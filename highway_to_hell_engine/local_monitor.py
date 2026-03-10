import time
import hashlib
import sys
import asyncio
from urllib.parse import quote_plus
from typing import Optional, Dict, Any, Tuple, List

import psutil

from .logging_setup import log

try:
    import win32gui  # type: ignore
    import win32process  # type: ignore
except Exception:
    win32gui = None
    win32process = None

try:
    from winsdk.windows.media.control import GlobalSystemMediaTransportControlsSessionManager
except Exception:
    GlobalSystemMediaTransportControlsSessionManager = None


def _get_windows_track_fast() -> Optional[Tuple[str, str]]:
    """Fallback: read track from Spotify window title."""
    if win32gui is None or win32process is None:
        return None

    try:
        spotify_pids = {
            p.info["pid"]
            for p in psutil.process_iter(["pid", "name"])
            if (p.info.get("name") or "").lower() == "spotify.exe"
        }
    except Exception:
        spotify_pids = set()

    windows: List[str] = []
    try:
        old_window = win32gui.FindWindow("SpotifyMainWindow", None)
        old = win32gui.GetWindowText(old_window)
        if old:
            windows.append(old)

        def enum_handler(hwnd, acc):
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
            except Exception:
                return
            if spotify_pids and pid not in spotify_pids:
                return

            text = win32gui.GetWindowText(hwnd)
            classname = win32gui.GetClassName(hwnd)
            if classname.startswith("Chrome_WidgetWin_") and text:
                acc.append(text)

        win32gui.EnumWindows(enum_handler, windows)
    except Exception:
        return None

    if not windows:
        return None

    windows = sorted(windows, key=len, reverse=True)
    title = windows[0]
    if title.lower().startswith("spotify"):
        return None

    try:
        artist, track = title.split(" - ", 1)
    except ValueError:
        artist = ""
        track = title

    track = (track or "").strip()
    artist = (artist or "").strip()
    if not track:
        return None

    return track, artist


async def _read_media_session_async() -> Optional[Dict[str, Any]]:
    if GlobalSystemMediaTransportControlsSessionManager is None:
        return None

    manager = await GlobalSystemMediaTransportControlsSessionManager.request_async()
    sessions = manager.get_sessions()
    if sessions.size == 0:
        return None

    spotify_session = None
    for s in sessions:
        src = (s.source_app_user_model_id or "").lower()
        if "spotify" in src:
            spotify_session = s
            break

    if spotify_session is None:
        return None

    playback = spotify_session.get_playback_info()
    # 4 = Playing (GlobalSystemMediaTransportControlsSessionPlaybackStatus.PLAYING)
    if int(playback.playback_status) != 4:
        return None

    timeline = spotify_session.get_timeline_properties()
    media = await spotify_session.try_get_media_properties_async()

    track = (media.title or "").strip()
    artist = (media.artist or "").strip()
    if not track:
        return None

    progress_ms = int(timeline.position.total_seconds() * 1000)
    duration_ms = int(timeline.end_time.total_seconds() * 1000)

    return {
        "track": track,
        "artist": artist,
        "progress_ms": max(0, progress_ms),
        "duration_ms": max(0, duration_ms),
    }


def _read_media_session_sync() -> Optional[Dict[str, Any]]:
    if GlobalSystemMediaTransportControlsSessionManager is None:
        return None
    try:
        return asyncio.run(_read_media_session_async())
    except RuntimeError:
        # Fallback if an event loop is already running in this thread.
        return None
    except Exception as e:
        log(f"Media session error: {e}", "DEBUG", "local")
        return None


class LocalSpotifyMonitor:
    """Local Spotify client monitor (no Premium required)."""

    def __init__(self, default_duration_ms: int = 300000):
        self._last_track_key: Optional[str] = None
        self._track_started_at: Optional[float] = None
        self._default_duration_ms = max(120000, int(default_duration_ms))

    def _fallback_track_state(self) -> Optional[Dict[str, Any]]:
        pair = _get_windows_track_fast()
        if not pair:
            return None

        track, artist = pair
        track_key = f"{artist.lower()}::{track.lower()}"
        now = time.time()

        if track_key != self._last_track_key:
            self._last_track_key = track_key
            self._track_started_at = now

        if self._track_started_at is None:
            self._track_started_at = now

        progress_ms = int(max(0.0, (now - self._track_started_at) * 1000.0))
        duration_ms = max(self._default_duration_ms, progress_ms + 120000)

        return {
            "track": track,
            "artist": artist,
            "progress_ms": progress_ms,
            "duration_ms": duration_ms,
            "duration_is_estimate": True,
        }

    def get_current_track(self) -> Optional[Dict[str, Any]]:
        state = None
        if sys.platform.startswith("win"):
            state = _read_media_session_sync()
            if state:
                state["duration_is_estimate"] = not bool(state.get("duration_ms"))
                if not state.get("duration_ms"):
                    state["duration_ms"] = max(self._default_duration_ms, int(state["progress_ms"]) + 120000)
            else:
                state = self._fallback_track_state()
        else:
            state = self._fallback_track_state()

        if not state:
            return None

        track = (state.get("track") or "").strip()
        artist = (state.get("artist") or "").strip()
        if not track:
            return None

        track_key = f"{artist.lower()}::{track.lower()}"
        track_id = hashlib.sha1(track_key.encode("utf-8")).hexdigest()[:22]

        return {
            "is_playing": True,
            "currently_playing_type": "track",
            "item": {
                "id": track_id,
                "name": track,
                "artists": [{"name": artist or "Unknown Artist"}],
                "duration_ms": int(state["duration_ms"]),
                "duration_is_estimate": bool(state.get("duration_is_estimate", False)),
                "external_urls": {
                    "spotify": f"https://open.spotify.com/search/{quote_plus((artist + ' ' + track).strip())}"
                },
            },
            "progress_ms": int(state["progress_ms"]),
            "timestamp": int(time.time() * 1000),
        }
