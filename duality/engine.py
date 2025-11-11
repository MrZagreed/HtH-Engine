import asyncio
import time
import traceback
from typing import List, Tuple, Dict, Any

from .logging_setup import log
from .display import SmartLyricsDisplay
from .rpc_client import safe_rpc_update
from .warp import TimeWarp

BAR_LEN = 14

def _bar(progress: int, duration: int) -> str:
    if duration <= 0:
        return "▱" * BAR_LEN
    progress = max(0, min(progress, duration))
    filled = int(BAR_LEN * progress / max(1, duration))
    return "▰" * filled + "▱" * (BAR_LEN - filled)

def _fmt_time(ms: int) -> str:
    ms = max(0, int(ms))
    s = ms // 1000
    return f"{s // 60:02d}:{s % 60:02d}"

def _clamp(v, lo, hi): 
    return lo if v < lo else hi if v > hi else v

async def lyrics_engine(
    song: str,
    artist: str,
    lyrics_data: List[Tuple[int, str]],
    duration_ms: int,
    url: str,
    rpc,
    rpc_lock,
    rpc_error_state,
    shutdown_event: asyncio.Event
):
    display = SmartLyricsDisplay(min_interval_s=0.2)
    warp = TimeWarp(max_drift_ms=7000, aggressive_correction=True)

    last_push_wall = time.time()
    last_pushed_ms: int | None = None
    last_update_time = 0.0
    heartbeat_every = 9.5

    stats = {"updates_sent": 0, "boundary_updates": 0, "heartbeat_updates": 0, "consecutive_failures": 0, "last_update_time": 0.0}

    flip = False
    ZERO_WIDTH = "\u200b"

    async def push(progress_ms: int, boundary: bool, force_update: bool):
        nonlocal last_update_time, flip
        # финальные клампы перед отрисовкой
        progress_ms = _clamp(progress_ms, 0, max(0, duration_ms))

        state = display.render(lyrics_data, progress_ms)
        bar = _bar(progress_ms, duration_ms)
        time_txt = f"{_fmt_time(progress_ms)} / {_fmt_time(duration_ms)}"

        flip = not flip
        suffix = ZERO_WIDTH if flip else ""

        payload: Dict[str, Any] = dict(
            details=f"{artist} — {song}"[:128],
            state=f"{state}\n{bar} {time_txt}{suffix}"[:128],
            large_image="spotify",
            large_text=song[:126],
            small_image="play",
            small_text="Текст песни",
            buttons=[{"label": "Слушать в Spotify", "url": url}],
            instance=True
        )

        now = time.time()
        if duration_ms > 0:
            payload.update({
                "start": int(now - (progress_ms / 1000.0)),
                "end": int(now + (max(0, duration_ms - progress_ms) / 1000.0))
            })

        success = await safe_rpc_update(rpc, payload, rpc_lock, rpc_error_state)
        if success:
            stats["last_update_time"] = now
            stats["consecutive_failures"] = 0
        else:
            stats["consecutive_failures"] += 1
            if stats["consecutive_failures"] > 3:
                log(f"МНОГО ОШИБОК RPC: {stats['consecutive_failures']} подряд", "WARNING", "engine")

        if boundary:
            stats["boundary_updates"] += 1
        else:
            stats["updates_sent"] += 1

    # Инициализация
    try:
        now_play = await asyncio.to_thread(rpc.spotify.current_user_playing_track)
    except Exception as e:
        log(f"Spotify API ошибка при старте движка: {e}", "ERROR", "engine")
        now_play = None

    if not now_play or not now_play.get("is_playing") or not now_play.get("item"):
        log("Нет активного трека, движок завершает работу", "WARNING", "engine")
        return

    init_progress = int(now_play.get("progress_ms") or 0)
    ts = int(now_play.get("timestamp") or int(time.time() * 1000))
    now_ms = int(time.time() * 1000)
    # Компенсация задержки клампится: от -0.5 до +1.5 сек
    lag_ms = _clamp(now_ms - ts, -500, 1500)
    init_reported_now = max(0, init_progress + lag_ms)

    last_pushed_ms = init_reported_now
    last_push_wall = time.time()
    warp.reset()

    corrected = warp.update(init_reported_now, last_pushed_ms, now=last_push_wall)
    await push(corrected, boundary=True, force_update=True)

    stagnation_count = 0
    last_idx = -1
    last_reported = init_reported_now

    while not shutdown_event.is_set():
        start_loop = time.time()
        try:
            now_play = await asyncio.to_thread(rpc.spotify.current_user_playing_track)
            if not now_play or not now_play.get("is_playing"):
                await asyncio.sleep(0.5)
                continue

            progress = int(now_play.get("progress_ms") or 0)
            ts = int(now_play.get("timestamp") or int(time.time() * 1000))
            now_ms = int(time.time() * 1000)
            lag_ms = _clamp(now_ms - ts, -500, 1500)
            reported_now = max(0, progress + lag_ms)

            # защита от аномальных скачков reported (редкие глюки API)
            if reported_now < last_reported - 3000:
                log(f"скачок назад в reported: {last_reported} -> {reported_now}, принудительный снап", "WARNING", "engine")
                reported_now = last_reported
            last_reported = reported_now

            # Что мы показываем: последний пуш + прошедшее локальное время
            shown_estimate = last_pushed_ms if last_pushed_ms is not None else reported_now
            dt = (time.time() - last_push_wall) * 1000.0
            shown_estimate = max(0, int(shown_estimate + dt))

            # жёсткий рельс: нельзя обгонять репорт более чем на 2 секунды
            lead_cap = 2000
            if shown_estimate > reported_now + lead_cap:
                shown_estimate = reported_now + lead_cap

            corrected = warp.update(reported_now, shown_estimate)

            # финальная страховка: не убегать от reported дальше чем на ±2с
            corrected = _clamp(corrected, reported_now - 2000, reported_now + 2000)
            corrected = _clamp(corrected, 0, max(0, duration_ms))

            # текущая строка для границ
            idx = -1
            for i in range(len(lyrics_data) - 1):
                if lyrics_data[i][0] <= corrected < lyrics_data[i+1][0]:
                    idx = i
                    break
            else:
                if lyrics_data and corrected >= lyrics_data[-1][0]:
                    idx = len(lyrics_data) - 1

            boundary = (idx != last_idx)
            last_idx = idx

            now_wall = time.time()
            force = False

            if reported_now <= init_reported_now:
                stagnation_count += 1
            else:
                stagnation_count = 0
                init_reported_now = reported_now

            if stagnation_count > 10:
                force = True
                log("Обнаружено залипание прогресса Spotify, принудительное обновление", "DEBUG", "engine")

            if (now_wall - stats["last_update_time"]) >= heartbeat_every:
                force = True
                stats["heartbeat_updates"] += 1

            min_interval = 0.9
            need_push = force or boundary or ((now_wall - last_update_time) >= min_interval)

            if need_push:
                await push(corrected, boundary, force)
                last_pushed_ms = corrected
                last_push_wall = now_wall
                last_update_time = now_wall

            processing_time = time.time() - start_loop
            sleep_time = max(0.05, 0.22 - processing_time)
            await asyncio.sleep(sleep_time)

        except asyncio.CancelledError:
            break
        except Exception as e:
            log(f"Критическая ошибка в движке: {e}", "ERROR", "engine")
            log(traceback.format_exc(), "DEBUG", "engine")
            await asyncio.sleep(1.0)

    log(
        f"ФИНАЛЬНАЯ СТАТИСТИКА ДВИЖКА: обновлений={stats['updates_sent'] + stats['boundary_updates'] + stats['heartbeat_updates']}, "
        f"коррекций времени={warp.total_corrections}",
        "INFO", "engine"
    )
