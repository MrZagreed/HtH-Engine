import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict

from .app_paths import CONFIG_FILE, ensure_app_dirs

LEGACY_CONFIG_FILE = Path(__file__).resolve().parent.parent / "highway_to_hell_engine_config.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "language": "en",
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

I18N: Dict[str, Dict[str, str]] = {
    "en": {
        "wizard_title": "FIRST-RUN SETUP WIZARD",
        "mode": "Mode",
        "discord_id": "Discord Client ID",
        "spotify_id": "Spotify Client ID",
        "spotify_secret": "Spotify Secret",
        "error_discord": "Error: Discord Client ID must contain 18-19 digits.",
        "error_api": "Error: API mode requires Spotify Client ID and Spotify Secret.",
        "env_loaded": "Configuration loaded from environment variables.",
        "warn_plain": "WARNING: secrets are stored in plain text in file",
        "warn_prod": "For production, use environment variables.",
        "saved": "Configuration saved to",
        "migrated": "Config migrated",
    },
    "ru": {
        "wizard_title": "МАСТЕР ПЕРВОГО ЗАПУСКА",
        "mode": "Режим",
        "discord_id": "Discord Client ID",
        "spotify_id": "Spotify Client ID",
        "spotify_secret": "Spotify Secret",
        "error_discord": "Ошибка: Discord Client ID должен содержать 18-19 цифр.",
        "error_api": "Ошибка: для API режима нужны Spotify Client ID и Spotify Secret.",
        "env_loaded": "Конфигурация загружена из переменных окружения.",
        "warn_plain": "ВНИМАНИЕ: секреты сохраняются в файл в открытом виде",
        "warn_prod": "Для production лучше использовать переменные окружения.",
        "saved": "Конфигурация сохранена в",
        "migrated": "Конфигурация перенесена",
    },
}


def _normalize_lang(lang: str | None) -> str:
    value = (lang or "").strip().lower()
    return value if value in {"en", "ru"} else "en"


def _t(lang: str, key: str) -> str:
    lang = _normalize_lang(lang)
    return I18N.get(lang, I18N["en"]).get(key, I18N["en"].get(key, key))


def _merge_defaults(data: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(DEFAULT_CONFIG)
    out.update(data)
    out["language"] = _normalize_lang(str(out.get("language", "en")))
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


def _migrate_legacy_config_if_needed(lang: str = "en") -> None:
    if CONFIG_FILE.exists() or not LEGACY_CONFIG_FILE.exists():
        return

    ensure_app_dirs()
    try:
        CONFIG_FILE.write_text(LEGACY_CONFIG_FILE.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"{_t(lang, 'migrated')}: {LEGACY_CONFIG_FILE.name} -> {CONFIG_FILE}")
    except Exception:
        pass


def _is_valid_discord_id(value: str) -> bool:
    return bool(re.match(r"^\d{18,19}$", value or ""))


def _prompt_config(mode: str, lang: str, existing: Dict[str, Any] | None = None) -> Dict[str, Any]:
    existing = existing or {}
    cfg = dict(existing)
    lang = _normalize_lang(lang)

    print("=" * 56)
    print(_t(lang, "wizard_title"))
    print("=" * 56)
    print(f"{_t(lang, 'mode')}: {mode.upper()}")

    discord_hint = f" [{cfg.get('discord_client_id')}]" if cfg.get("discord_client_id") else ""
    discord_id = input(f"{_t(lang, 'discord_id')}{discord_hint}: ").strip() or str(cfg.get("discord_client_id", "")).strip()
    if not _is_valid_discord_id(discord_id):
        print(_t(lang, "error_discord"))
        sys.exit(1)
    cfg["discord_client_id"] = discord_id

    if mode == "api":
        sp_id_hint = f" [{cfg.get('spotify_client_id')}]" if cfg.get("spotify_client_id") else ""
        sp_secret_hint = f" [{cfg.get('spotify_secret')}]" if cfg.get("spotify_secret") else ""

        spotify_client_id = input(f"{_t(lang, 'spotify_id')}{sp_id_hint}: ").strip() or str(cfg.get("spotify_client_id", "")).strip()
        spotify_secret = input(f"{_t(lang, 'spotify_secret')}{sp_secret_hint}: ").strip() or str(cfg.get("spotify_secret", "")).strip()

        if not spotify_client_id or not spotify_secret:
            print(_t(lang, "error_api"))
            sys.exit(1)

        cfg["spotify_client_id"] = spotify_client_id
        cfg["spotify_secret"] = spotify_secret
    else:
        cfg.setdefault("spotify_client_id", "")
        cfg.setdefault("spotify_secret", "")

    cfg["language"] = lang
    return _merge_defaults(cfg)


def _validate_for_mode(cfg: Dict[str, Any], mode: str) -> bool:
    for key in _required_keys_for_mode(mode):
        if not cfg.get(key):
            return False
    return _is_valid_discord_id(str(cfg.get("discord_client_id", "")))


def load_or_create_config(mode: str = "api", lang: str = "en") -> Dict[str, Any]:
    """
    Loads configuration from file/environment variables.
    If data is insufficient for selected mode, starts setup wizard.
    """
    mode = (mode or "api").lower().strip()
    if mode not in {"api", "local"}:
        mode = "api"

    lang = _normalize_lang(lang)

    ensure_app_dirs()
    _migrate_legacy_config_if_needed(lang=lang)

    file_cfg = _load_config_file(CONFIG_FILE) if CONFIG_FILE.exists() else None
    if file_cfg:
        stored_lang = _normalize_lang(str(file_cfg.get("language", "en")))
        if lang == "en" and stored_lang in {"en", "ru"}:
            lang = stored_lang
        file_cfg["language"] = lang
        if _validate_for_mode(file_cfg, mode):
            return file_cfg

    env_cfg = {
        "discord_client_id": os.environ.get("DISCORD_CLIENT_ID", "").strip(),
        "spotify_client_id": os.environ.get("SPOTIFY_CLIENT_ID", "").strip(),
        "spotify_secret": os.environ.get("SPOTIFY_SECRET", "").strip(),
        "language": _normalize_lang(os.environ.get("APP_LANG", lang)),
    }
    env_cfg = _merge_defaults(env_cfg)
    if _validate_for_mode(env_cfg, mode):
        print(_t(lang, "env_loaded"))
        return env_cfg

    prepared = _prompt_config(mode=mode, lang=lang, existing=file_cfg or env_cfg)

    print(f"\n{_t(lang, 'warn_plain')}")
    print(CONFIG_FILE)
    print(_t(lang, "warn_prod"))

    CONFIG_FILE.write_text(json.dumps(prepared, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{_t(lang, 'saved')} {CONFIG_FILE}")
    return prepared
