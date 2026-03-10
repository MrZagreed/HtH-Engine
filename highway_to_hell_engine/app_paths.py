from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "highway_to_hell_engine_data"
CONFIG_DIR = DATA_DIR / "config"
CACHE_DIR = DATA_DIR / "cache"

CONFIG_FILE = CONFIG_DIR / "highway_to_hell_engine_config.json"
LYRICS_DB_FILE = CACHE_DIR / "lyrics_cache.db"
SPOTIFY_CACHE_FILE = CACHE_DIR / "spotify_oauth_cache.json"


def ensure_app_dirs() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
