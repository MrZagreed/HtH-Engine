import platform, json, time
from pathlib import Path
from typing import Dict, Any
from .logging_setup import log
try:
    import psutil
except Exception:
    psutil = None

def env_report() -> Dict[str,Any]:
    rep = {
        "python": platform.python_version(),
        "impl": platform.python_implementation(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
    }
    return rep

def discord_running() -> bool:
    if psutil is None: return False
    try:
        for p in psutil.process_iter(attrs=["name"]):
            if (p.info.get("name") or "").lower().startswith("discord"):
                return True
    except Exception: pass
    return False

def write_report(path: Path):
    data = dict(env=env_report(), ts=time.time())
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def is_spotify_ad(current: dict) -> bool:
    if not current: return False
    # Явный флаг типа "ad"
    t = current.get("currently_playing_type")
    if t == "ad": return True
    item = current.get("item")
    if not item: return True  # во время рекламы API часто возвращает item=None
    # эвристики
    name = (item.get("name") or "").lower()
    art = (item.get("artists",[{"name":""}])[0].get("name") or "").lower()
    return "advert" in name or "spotify" == art

__all__ = ["env_report", "discord_running", "write_report", "is_spotify_ad"]
