import asyncio
import time
import traceback
from urllib.parse import urlparse
from typing import List, Tuple, Dict, Any, Callable, Optional

from .logging_setup import log
from .display import SmartLyricsDisplay
from .rpc_client import safe_rpc_update
from .warp import TimeWarp

BAR_LEN = 14
MIN_BAR_LEN = 6


def _bar(progress: int, duration: int, length: int = BAR_LEN) -> str:
    length = max(MIN_BAR_LEN, int(length))
    if duration <= 0:
        return "▱" * length
    progress = max(0, min(progress, duration))
    filled = int(length * progress / max(1, duration))
    return "▰" * filled + "▱" * (length - filled)

def _fmt_time(ms: int) -> str:
    ms = max(0, int(ms))
    s = ms // 1000
    return f"{s // 60:02d}:{s % 60:02d}"

def _clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v

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


def _compose_rpc_state(lyrics_state: str, progress_ms: int, duration_ms: int, suffix: str) -> str:
    """Keep lyrics block priority (2.5 lines), adapt bar/time footer to fit 128 chars."""
    body = (lyrics_state or "").strip("\n")
    if len(body) >= 128:
        return body[:128]

    time_full = f"{_fmt_time(progress_ms)} / {_fmt_time(duration_ms)}"
    time_short = f"{_fmt_time(progress_ms)}"
    variants = [
        f"{_bar(progress_ms, duration_ms, BAR_LEN)} {time_full}{suffix}",
        f"{_bar(progress_ms, duration_ms, 10)} {time_full}{suffix}",
        f"{_bar(progress_ms, duration_ms, 10)} {time_short}{suffix}",
        f"{_bar(progress_ms, duration_ms, BAR_LEN)}{suffix}",
        f"{_bar(progress_ms, duration_ms, 10)}{suffix}",
        f"{_bar(progress_ms, duration_ms, 8)}{suffix}",
        f"{_bar(progress_ms, duration_ms, MIN_BAR_LEN)}{suffix}",
    ]

    for footer in variants:
        candidate = f"{body}\n{footer}" if body else footer
        if len(candidate) <= 128:
            return candidate

    return body[:128]

async def lyrics_engine(
    song: str,
    artist: str,
    lyrics_data: List[Tuple[int, str]],
    duration_state: Dict[str, Any],
    url: str,
    rpc,
    rpc_lock,
    rpc_error_state,
    shutdown_event: asyncio.Event,
    get_track_func: Callable[[], Optional[Dict[str, Any]]],
    config: dict  # config parameter
):
    display = SmartLyricsDisplay(
        max_lines=int(config.get("lyrics_rpc_lines", 3)),
        max_line_length=int(config.get("lyrics_rpc_line_length", 26)),
        min_interval_s=float(config.get("lyrics_rpc_render_interval", 0.2)),
        page_flip_interval_s=float(config.get("lyrics_rpc_page_flip_interval", 0.9)),
        next_preview_ratio=float(config.get("lyrics_rpc_next_preview_ratio", 0.5)),
    )
    warp = TimeWarp(
        max_drift_ms=config.get("max_drift_ms", 7000),
        aggressive_correction=config.get("aggressive_correction", True)
    )

    last_push_wall = time.time()
    last_pushed_ms: Optional[int] = None
    last_update_time = 0.0
    heartbeat_every = config.get("heartbeat_interval", 9.5)

    stats = {
        "updates_sent": 0,
        "boundary_updates": 0,
        "heartbeat_updates": 0,
        "consecutive_failures": 0,
        "last_update_time": 0.0
    }

    flip = False
    ZERO_WIDTH = "\u200b"

    async def push(progress_ms: int, boundary: bool, force_update: bool):
        nonlocal last_update_time, flip
        current_duration_ms = int(duration_state.get("ms", 0) or 0)
        duration_is_estimate = bool(duration_state.get("estimated", False))
        progress_ms = _clamp(progress_ms, 0, max(0, current_duration_ms))

        state = display.render(lyrics_data, progress_ms)

        flip = not flip
        suffix = ZERO_WIDTH if flip else ""

        payload: Dict[str, Any] = {
            "details": f"{artist} - {song}"[:128],
            "state": _compose_rpc_state(state, progress_ms, current_duration_ms, suffix),
            "instance": True
        }

        safe_url = _safe_spotify_url(url)
        if safe_url:
            payload["buttons"] = [{"label": "Open in Spotify", "url": safe_url}]

        large_image = config.get("discord_large_image")
        if large_image:
            payload["large_image"] = str(large_image)
            payload["large_text"] = str(config.get("discord_hover_text", "Discord Karaoke RPC by Mr.Zagreed"))[:126]

        small_image = config.get("discord_small_image")
        if small_image:
            payload["small_image"] = str(small_image)
            payload["small_text"] = "Lyrics Sync"

        now = time.time()
        if current_duration_ms > 0:
            payload["start"] = int(now - (progress_ms / 1000.0))
            if (not duration_is_estimate) or len(lyrics_data) >= 2:
                payload["end"] = int(now + (max(0, current_duration_ms - progress_ms) / 1000.0))

        success = await safe_rpc_update(rpc, payload, rpc_lock, rpc_error_state)
        if success:
            stats["last_update_time"] = now
            stats["consecutive_failures"] = 0
        else:
            stats["consecutive_failures"] += 1
            if stats["consecutive_failures"] > 3:
                log(f"Many RPC errors: {stats['consecutive_failures']} in a row", "WARNING", "engine")

        if boundary:
            stats["boundary_updates"] += 1
        else:
            stats["updates_sent"] += 1

    try:
        now_play = await asyncio.to_thread(get_track_func)
    except Exception as e:
        log(f"Failed to read track at engine startup: {e}", "ERROR", "engine")
        now_play = None

    if not now_play or not now_play.get("is_playing") or not now_play.get("item"):
        log("No active track. Engine exits.", "WARNING", "engine")
        return

    init_progress = int(now_play.get("progress_ms") or 0)
    ts = int(now_play.get("timestamp") or int(time.time() * 1000))
    now_ms = int(time.time() * 1000)
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
    last_seek_resync_log_ts = 0.0

    while not shutdown_event.is_set():
        start_loop = time.time()
        try:
            now_play = await asyncio.to_thread(get_track_func)
            if not now_play or not now_play.get("is_playing"):
                await asyncio.sleep(0.5)
                continue

            progress = int(now_play.get("progress_ms") or 0)
            ts = int(now_play.get("timestamp") or int(time.time() * 1000))
            now_ms = int(time.time() * 1000)
            lag_ms = _clamp(now_ms - ts, -500, 1500)
            reported_now = max(0, progress + lag_ms)

            if reported_now < last_reported - 3000:
                backward_delta = last_reported - reported_now
                if backward_delta >= 15000 or reported_now <= 5000:
                    now_ts = time.time()
                    if now_ts - last_seek_resync_log_ts >= 3.0:
                        log(
                            f"Detected playback seek/restart: {last_reported} -> {reported_now}, resyncing timeline",
                            "INFO",
                            "engine",
                        )
                        last_seek_resync_log_ts = now_ts

                    warp.reset()
                    last_reported = reported_now
                    init_reported_now = reported_now
                    last_pushed_ms = reported_now
                    last_push_wall = now_ts
                    await push(reported_now, boundary=True, force_update=True)
                    await asyncio.sleep(0.05)
                    continue

                log(f"Backward jump in reported progress: {last_reported} -> {reported_now}, forcing snap", "WARNING", "engine")
                reported_now = last_reported
            last_reported = reported_now
            shown_estimate = last_pushed_ms if last_pushed_ms is not None else reported_now
            dt = (time.time() - last_push_wall) * 1000.0
            shown_estimate = max(0, int(shown_estimate + dt))

            lead_cap = 2000
            if shown_estimate > reported_now + lead_cap:
                shown_estimate = reported_now + lead_cap

            corrected = warp.update(reported_now, shown_estimate)
            corrected = _clamp(corrected, reported_now - 2000, reported_now + 2000)
            corrected = _clamp(corrected, 0, max(0, int(duration_state.get("ms", 0) or 0)))

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
                log("Spotify progress appears stalled, forcing update", "DEBUG", "engine")

            if (now_wall - stats["last_update_time"]) >= heartbeat_every:
                force = True
                stats["heartbeat_updates"] += 1

            min_interval = config.get("min_update_interval", 1.2)
            need_push = force or boundary or ((now_wall - last_update_time) >= min_interval)

            if need_push:
                await push(corrected, boundary, force)
                last_pushed_ms = corrected
                last_push_wall = now_wall
                last_update_time = now_wall

            processing_time = time.time() - start_loop
            sleep_time = max(0.05, 1.0 - processing_time)  # tuned sleep floor
            await asyncio.sleep(sleep_time)

        except asyncio.CancelledError:
            break
        except Exception as e:
            log(f"Critical engine error: {e}", "ERROR", "engine")
            log(traceback.format_exc(), "DEBUG", "engine")
            await asyncio.sleep(1.0)

    log(
        f"FINAL ENGINE STATS: updates={stats['updates_sent'] + stats['boundary_updates'] + stats['heartbeat_updates']}, "
        f"time corrections={warp.total_corrections}",
        "INFO", "engine"
    )

