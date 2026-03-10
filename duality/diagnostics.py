import json
import platform
import time
from pathlib import Path
from typing import Dict, Any

from .logging_setup import log

try:
    import psutil
except ImportError:
    psutil = None
    log("psutil не установлен — функции диагностики ограничены.", "WARNING", "diagnostics")

def env_report() -> Dict[str, Any]:
    return {
        "python": platform.python_version(),
        "impl": platform.python_implementation(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
    }

def discord_running() -> bool:
    if psutil is None:
        return False
    try:
        for p in psutil.process_iter(attrs=["name"]):
            name = (p.info.get("name") or "").lower()
            if name.startswith("discord"):
                return True
    except Exception:
        pass
    return False

def write_report(path: Path):
    data = {"env": env_report(), "ts": time.time()}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def is_spotify_ad(current: dict) -> bool:
    """
    Улучшенное определение рекламы.
    """
    if not current:
        return False

    # Явный тип
    if current.get("currently_playing_type") == "ad":
        return True

    item = current.get("item")
    # Если нет item — скорее всего реклама (или ошибка)
    if not item:
        return True

    # Эвристики по названию и исполнителю
    name = (item.get("name") or "").lower()
    artists = item.get("artists") or [{}]
    artist_name = (artists[0].get("name") or "").lower()

    # Список триггерных слов
    ad_keywords = ["advert", "advertisement", "spotify", "реклама"]
    for kw in ad_keywords:
        if kw in name or kw in artist_name:
            return True

    # Короткие треки (< 30 сек) часто реклама
    duration = item.get("duration_ms") or 0
    if 0 < duration < 30000:
        return True

    return False

__all__ = ["env_report", "discord_running", "write_report", "is_spotify_ad"]
