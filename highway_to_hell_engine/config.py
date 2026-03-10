import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict

from .app_paths import CONFIG_FILE, ensure_app_dirs

LEGACY_CONFIG_FILE = Path(__file__).resolve().parent.parent / "highway_to_hell_engine_config.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "discord_hover_text": "Discord Karaoke RPC by Mr.Zagreed",
    "discord_large_image": "spotify",
    "discord_small_image": "",
    "cache_ttl": 2.0,
    "cache_ttl_local": 0.5,
    "poll_interval": 1.0,
    "poll_interval_local": 0.5,
    "min_update_interval": 1.2,
    "heartbeat_interval": 9.5,
    "max_drift_ms": 7000,
    "aggressive_correction": True,
}


def _merge_defaults(data: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(DEFAULT_CONFIG)
    out.update(data)
    return out


def _required_keys_for_mode(mode: str) -> tuple[str, ...]:
    if mode == "api":
        return ("discord_client_id", "spotify_client_id", "spotify_secret")
    return ("discord_client_id",)


def _load_config_file(path: Path) -> Dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    return _merge_defaults(data)


def _migrate_legacy_config_if_needed() -> None:
    if CONFIG_FILE.exists() or not LEGACY_CONFIG_FILE.exists():
        return

    ensure_app_dirs()
    try:
        CONFIG_FILE.write_text(LEGACY_CONFIG_FILE.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"Config migrated: {LEGACY_CONFIG_FILE.name} -> {CONFIG_FILE}")
    except Exception:
        pass


def _is_valid_discord_id(value: str) -> bool:
    return bool(re.match(r"^\d{18,19}$", value or ""))


def _prompt_config(mode: str, existing: Dict[str, Any] | None = None) -> Dict[str, Any]:
    existing = existing or {}
    cfg = dict(existing)

    print("=" * 56)
    print("FIRST-RUN SETUP WIZARD")
    print("=" * 56)
    print(f"Mode: {mode.upper()}")

    discord_hint = f" [{cfg.get('discord_client_id')}]" if cfg.get("discord_client_id") else ""
    discord_id = input(f"Discord Client ID{discord_hint}: ").strip() or str(cfg.get("discord_client_id", "")).strip()
    if not _is_valid_discord_id(discord_id):
        print("Error: Discord Client ID must contain 18-19 digits.")
        sys.exit(1)
    cfg["discord_client_id"] = discord_id

    if mode == "api":
        sp_id_hint = f" [{cfg.get('spotify_client_id')}]" if cfg.get("spotify_client_id") else ""
        sp_secret_hint = f" [{cfg.get('spotify_secret')}]" if cfg.get("spotify_secret") else ""

        spotify_client_id = input(f"Spotify Client ID{sp_id_hint}: ").strip() or str(cfg.get("spotify_client_id", "")).strip()
        spotify_secret = input(f"Spotify Secret{sp_secret_hint}: ").strip() or str(cfg.get("spotify_secret", "")).strip()

        if not spotify_client_id or not spotify_secret:
            print("Error: API mode requires Spotify Client ID and Spotify Secret.")
            sys.exit(1)

        cfg["spotify_client_id"] = spotify_client_id
        cfg["spotify_secret"] = spotify_secret
    else:
        # Spotify API credentials are optional in local mode.
        cfg.setdefault("spotify_client_id", "")
        cfg.setdefault("spotify_secret", "")

    return _merge_defaults(cfg)


def _validate_for_mode(cfg: Dict[str, Any], mode: str) -> bool:
    for key in _required_keys_for_mode(mode):
        if not cfg.get(key):
            return False
    return _is_valid_discord_id(str(cfg.get("discord_client_id", "")))


def load_or_create_config(mode: str = "api") -> Dict[str, Any]:
    """
    Loads configuration from file/environment variables.
    If data is insufficient for selected mode, starts setup wizard.
    """
    mode = (mode or "api").lower().strip()
    if mode not in {"api", "local"}:
        mode = "api"

    ensure_app_dirs()
    _migrate_legacy_config_if_needed()

    file_cfg = _load_config_file(CONFIG_FILE) if CONFIG_FILE.exists() else None
    if file_cfg and _validate_for_mode(file_cfg, mode):
        return file_cfg

    env_cfg = {
        "discord_client_id": os.environ.get("DISCORD_CLIENT_ID", "").strip(),
        "spotify_client_id": os.environ.get("SPOTIFY_CLIENT_ID", "").strip(),
        "spotify_secret": os.environ.get("SPOTIFY_SECRET", "").strip(),
    }
    env_cfg = _merge_defaults(env_cfg)
    if _validate_for_mode(env_cfg, mode):
        print("Configuration loaded from environment variables.")
        return env_cfg

    prepared = _prompt_config(mode, existing=file_cfg or env_cfg)

    print("\nWARNING: secrets are stored in plain text in file")
    print(CONFIG_FILE)
    print("For production, use environment variables.")

    CONFIG_FILE.write_text(json.dumps(prepared, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Configuration saved to {CONFIG_FILE}")
    return prepared
