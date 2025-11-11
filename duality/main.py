import asyncio, time, traceback, warnings
from typing import Any, Dict
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
from pypresence import AioPresence
from .logging_setup import log, LOG_FILE, DEBUG_LOG_FILE
from .server import LocalHttpsServer
from .lyrics import fetch_lyrics
from .engine import lyrics_engine
from .network import NetworkMonitor
from .diagnostics import discord_running, is_spotify_ad

async def run_presence(config: Dict[str,Any], shutdown_event: asyncio.Event):
    # Discord
    try:
        rpc = AioPresence(config["discord_client_id"])
        await rpc.connect()
        log("RPC подключено", "INFO", "main")
    except Exception as e:
        log(f"Не удалось подключиться к Discord RPC: {e}", "ERROR", "main")
        if not discord_running():
            log("Discord не запущен. Ожидание запуска и повторные попытки...", "WARNING", "main")
        # продолжаем попытки в фоне
        async def ensure():
            while not shutdown_event.is_set():
                try:
                    await rpc.connect()
                    return
                except Exception: 
                    await asyncio.sleep(2.0)
        asyncio.create_task(ensure())

    # Spotify
    server = LocalHttpsServer(8888)
    redirect_uri = await server.start()
    sp = Spotify(auth_manager=SpotifyOAuth(
        client_id=config["spotify_client_id"],
        client_secret=config["spotify_secret"],
        redirect_uri=redirect_uri,
        scope="user-read-currently-playing user-read-playback-state",
        cache_path=".spotify_cache",
        open_browser=False
    ))
    # Сохраняем ссылку на Spotify клиент внутрь rpc для удобства вызовов из движка
    rpc.spotify = sp

    rpc_lock = asyncio.Lock()
    rpc_error = {"fails": 0, "suspended": False}
    net = NetworkMonitor()

    lyrics_task = None
    current_track_id = None

    log("Запуск основного цикла…", "INFO", "main")
    while not shutdown_event.is_set():
        # Исправленный вызов метода check
        net.check()
        
        try:
            tr = sp.current_user_playing_track()
        except Exception as e:
            log(f"Spotify API ошибка: {e}", "ERROR", "main")
            await asyncio.sleep(0.5)
            continue

        if not tr or not tr.get("is_playing"):
            await asyncio.sleep(0.3)
            continue

        if is_spotify_ad(tr):
            # Во время рекламы не спамим запросами за текстом, выводим заглушку.
            payload = dict(details="Реклама в Spotify",
                           state="Подождите окончание блока…",
                           large_image="spotify", small_image="pause")
            try:
                async with rpc_lock:
                    await rpc.update(**payload)
            except Exception:
                pass
            await asyncio.sleep(1.0)
            continue

        item = tr.get("item")
        if not item:
            await asyncio.sleep(0.2)
            continue

        song = item["name"]
        artist = item["artists"][0]["name"]
        url = item["external_urls"]["spotify"]
        tid = item["id"]
        dur = int(item["duration_ms"])

        if tid != current_track_id:
            current_track_id = tid
            if lyrics_task and not lyrics_task.done():
                lyrics_task.cancel()
                try: 
                    await lyrics_task
                except asyncio.CancelledError: 
                    pass
            
            lines = fetch_lyrics(song, artist, dur)
            log(f"Текст: {len(lines)} строк → {song} — {artist}", "INFO", "lyrics")
            
            lyrics_task = asyncio.create_task(
                lyrics_engine(song, artist, lines, dur, url, rpc, rpc_lock, rpc_error, shutdown_event)
            )

        await asyncio.sleep(0.3)

    try:
        if lyrics_task: 
            lyrics_task.cancel()
        await server.stop()
    finally:
        try:
            await rpc.clear()
            await rpc.close()
        except Exception: 
            pass

async def main(config: Dict[str,Any]):
    log("=== ЗАПУСК SPOTIFY DISCORD LYRICS PRESENCE ===", "INFO", "main")
    log(f"Основной лог: {LOG_FILE}", "INFO", "main")
    log(f"Отладочный лог: {DEBUG_LOG_FILE}", "INFO", "main")
    shutdown_event = asyncio.Event()
    try:
        await run_presence(config, shutdown_event)
    except KeyboardInterrupt:
        log("Получен сигнал прерывания", "INFO", "main")
    except Exception as e:
        log(f"Критическая ошибка: {e}", "CRITICAL", "main")
        log(traceback.format_exc(), "DEBUG", "main")
    finally:
        shutdown_event.set()
        log("Приложение завершено", "INFO", "main")