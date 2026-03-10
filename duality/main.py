import asyncio
import time
import traceback
from urllib.parse import urlparse
from typing import Any, Dict, Callable, Optional

from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
from pypresence import AioPresence

from .logging_setup import log, LOG_FILE, DEBUG_LOG_FILE
from .server import LocalHttpsServer
from .lyrics import fetch_lyrics
from .engine import lyrics_engine
from .network import NetworkMonitor
from .diagnostics import discord_running, is_spotify_ad
from .app_paths import SPOTIFY_CACHE_FILE, ensure_app_dirs
from . import __version__

# Тип функции получения текущего трека
GetTrackFunc = Callable[[], Optional[Dict[str, Any]]]


def _presence_assets(config: Dict[str, Any]) -> Dict[str, str]:
    payload: Dict[str, str] = {}
    large_image = config.get("discord_large_image")
    hover_text = str(config.get("discord_hover_text", "Discord Karaoke RPC by Mr.Zagreed"))[:126]
    if large_image:
        payload["large_image"] = str(large_image)
        payload["large_text"] = hover_text

    small_image = config.get("discord_small_image")
    if small_image:
        payload["small_image"] = str(small_image)
        payload["small_text"] = "Lyrics Sync"
    return payload

def _safe_spotify_url(url: str) -> Optional[str]:
    try:
        parsed = urlparse((url or "").strip())
        if parsed.scheme != "https":
            return None
        if parsed.netloc.lower() not in {"open.spotify.com", "spotify.link"}:
            return None
        return parsed.geturl()
    except Exception:
        return None


def _buttons_payload(url: str) -> Optional[list[Dict[str, str]]]:
    safe = _safe_spotify_url(url)
    if not safe:
        return None
    return [{"label": "Open in Spotify", "url": safe}]

class TrackCache:
    """Простое кэширование данных трека для уменьшения числа запросов к API."""
    def __init__(self, ttl: float = 2.0):
        self.ttl = ttl
        self._data: Optional[Dict[str, Any]] = None
        self._timestamp = 0.0

    def get(self, func: GetTrackFunc) -> Optional[Dict[str, Any]]:
        now = time.time()
        if self._data is not None and (now - self._timestamp) < self.ttl:
            return self._data
        try:
            self._data = func()
            self._timestamp = now
        except Exception:
            self._data = None
        return self._data

async def _load_lyrics_background(lines_target: list, duration_state: Dict[str, Any], song: str, artist: str, dur: int) -> None:
    log(f"Загрузка текста: {song} — {artist}", "INFO", "lyrics")
    try:
        lines = await asyncio.to_thread(fetch_lyrics, song, artist, dur)
    except asyncio.CancelledError:
        return
    except Exception as e:
        log(f"Ошибка загрузки текста: {e}", "ERROR", "lyrics")
        lines = []

    lines_target.clear()
    lines_target.extend(lines)

    if lines_target:
        last_ts = int(lines_target[-1][0])
        if 60_000 <= last_ts <= 1_200_000:
            detected_ms = last_ts + 2500
            if bool(duration_state.get("estimated", False)):
                duration_state["ms"] = detected_ms
            else:
                duration_state["ms"] = max(detected_ms, int(duration_state.get("ms", dur)))
            duration_state["estimated"] = False

    log(f"Текст: {len(lines_target)} строк -> {song} — {artist}", "INFO", "lyrics")

async def run_presence(
    config: Dict[str, Any],
    shutdown_event: asyncio.Event,
    mode: str
) -> None:
    ensure_app_dirs()

    # ---------- Discord RPC ----------
    try:
        rpc = AioPresence(config["discord_client_id"])
        await rpc.connect()
        log("RPC подключено", "INFO", "main")
    except Exception as e:
        log(f"Не удалось подключиться к Discord RPC: {e}", "ERROR", "main")
        if not discord_running():
            log("Discord не запущен. Ожидание запуска...", "WARNING", "main")
        async def ensure():
            while not shutdown_event.is_set():
                try:
                    await rpc.connect()
                    return
                except Exception:
                    await asyncio.sleep(2.0)
        asyncio.create_task(ensure())

    # ---------- Выбор источника данных ----------
    get_track_func: GetTrackFunc
    server = None

    if mode == 'api':
        server = LocalHttpsServer(8888)
        redirect_uri = await server.start()
        sp = Spotify(auth_manager=SpotifyOAuth(
            client_id=config["spotify_client_id"],
            client_secret=config["spotify_secret"],
            redirect_uri=redirect_uri,
            scope="user-read-currently-playing user-read-playback-state",
            cache_path=str(SPOTIFY_CACHE_FILE),
            open_browser=False
        ))
        rpc.spotify = sp  # для обратной совместимости
        get_track_func = lambda: sp.current_user_playing_track()
        log("Режим API: используется Web API (требуется Premium)", "INFO", "main")
    else:  # local
        try:
            from .local_monitor import LocalSpotifyMonitor
        except ImportError as e:
            log(f"Модуль local_monitor не найден: {e}. Установите swspotify.", "ERROR", "main")
            return
        monitor = LocalSpotifyMonitor()
        get_track_func = monitor.get_current_track
        rpc.spotify = None
        log("Режим LOCAL: отслеживание локального клиента Spotify (без Premium)", "INFO", "main")

    # ---------- Общие компоненты ----------
    rpc_lock = asyncio.Lock()
    rpc_error = {"fails": 0, "suspended": False}
    net = NetworkMonitor()
    cache_ttl = config.get("cache_ttl_local", 0.35) if mode == "local" else config.get("cache_ttl", 2.0)
    poll_interval = config.get("poll_interval_local", 0.35) if mode == "local" else config.get("poll_interval", 1.0)
    track_cache = TrackCache(ttl=cache_ttl)

    lyrics_task: Optional[asyncio.Task] = None
    lyrics_loader_task: Optional[asyncio.Task] = None
    current_track_id = None
    idle_presence_sent = False
    last_wait_log = 0.0

    log("Запуск основного цикла…", "INFO", "main")
    while not shutdown_event.is_set():
        # Проверка сети перед запросом
        if not net.check():
            await asyncio.sleep(5)
            continue

        try:
            tr = await asyncio.to_thread(track_cache.get, get_track_func)
        except Exception as e:
            log(f"Ошибка получения трека: {e}", "ERROR", "main")
            await asyncio.sleep(1.0)
            continue

        if not tr or not tr.get("is_playing"):
            now = time.time()
            if now - last_wait_log >= 15:
                log("Ожидание: Spotify не воспроизводит трек или данные недоступны", "INFO", "main")
                last_wait_log = now

            if not idle_presence_sent:
                payload = {
                    "details": "Spotify запущен",
                    "state": "Ожидание воспроизведения трека",
                }
                payload.update(_presence_assets(config))
                try:
                    async with rpc_lock:
                        await rpc.update(**payload)
                    idle_presence_sent = True
                except Exception as e:
                    log(f"Не удалось обновить RPC в режиме ожидания: {e}", "DEBUG", "main")

            await asyncio.sleep(0.5)
            continue

        # Определение рекламы (унифицированная функция)
        is_ad = is_spotify_ad(tr)
        if is_ad:
            payload = {
                "details": "Реклама в Spotify",
                "state": "Подождите окончание блока…",
            }
            payload.update(_presence_assets(config))
            try:
                async with rpc_lock:
                    await rpc.update(**payload)
            except Exception as e:
                log(f"Не удалось обновить RPC в режиме рекламы: {e}", "DEBUG", "main")
            await asyncio.sleep(1.0)
            continue

        item = tr.get("item")
        if not item:
            await asyncio.sleep(0.2)
            continue

        idle_presence_sent = False

        song = item["name"]
        artist = item["artists"][0]["name"]
        url = item["external_urls"]["spotify"]
        tid = item["id"]
        dur = int(item["duration_ms"])
        duration_is_estimate = bool(item.get("duration_is_estimate", False))

        if tid != current_track_id:
            current_track_id = tid
            if lyrics_task and not lyrics_task.done():
                lyrics_task.cancel()
                try:
                    await lyrics_task
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    log(f"Ошибка при отмене предыдущей задачи: {e}", "ERROR", "main")

            if lyrics_loader_task and not lyrics_loader_task.done():
                lyrics_loader_task.cancel()

            progress_ms = int(tr.get("progress_ms") or 0)
            try:
                payload = {
                    "details": f"{artist} — {song}"[:128],
                    "state": "Синхронизация текста...",
                    "instance": True,
                }
                buttons = _buttons_payload(url)
                if buttons:
                    payload["buttons"] = buttons
                payload.update(_presence_assets(config))
                now = time.time()
                if dur > 0:
                    payload["start"] = int(now - (progress_ms / 1000.0))
                    if not duration_is_estimate:
                        payload["end"] = int(now + (max(0, dur - progress_ms) / 1000.0))
                async with rpc_lock:
                    await rpc.update(**payload)
            except Exception as e:
                log(f"Не удалось отправить мгновенный RPC апдейт: {e}", "DEBUG", "main")

            lines: list[tuple[int, str]] = []
            duration_state: Dict[str, Any] = {"ms": dur, "estimated": duration_is_estimate}
            lyrics_loader_task = asyncio.create_task(_load_lyrics_background(lines, duration_state, song, artist, dur))

            lyrics_task = asyncio.create_task(
                lyrics_engine(
                    song, artist, lines, duration_state, url,
                    rpc, rpc_lock, rpc_error, shutdown_event,
                    get_track_func,
                    config
                )
            )

        await asyncio.sleep(poll_interval)

    # Завершение
    try:
        if lyrics_task:
            lyrics_task.cancel()
        if lyrics_loader_task:
            lyrics_loader_task.cancel()
        if server:
            await server.stop()
    finally:
        try:
            await rpc.clear()
            await rpc.close()
        except Exception:
            pass

async def main(config: Dict[str, Any], mode: str = 'api') -> None:
    log(f"=== ЗАПУСК SPOTIFY DISCORD LYRICS PRESENCE v{__version__} ===", "INFO", "main")
    log(f"Режим работы: {mode.upper()}", "INFO", "main")
    log(f"Основной лог: {LOG_FILE}", "INFO", "main")
    log(f"Отладочный лог: {DEBUG_LOG_FILE}", "INFO", "main")

    shutdown_event = asyncio.Event()
    try:
        await run_presence(config, shutdown_event, mode)
    except KeyboardInterrupt:
        log("Получен сигнал прерывания", "INFO", "main")
    except Exception as e:
        log(f"Критическая ошибка: {e}", "CRITICAL", "main")
        log(traceback.format_exc(), "DEBUG", "main")
    finally:
        shutdown_event.set()
        log("Приложение завершено", "INFO", "main")