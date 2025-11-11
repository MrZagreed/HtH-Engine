import json, sys
from pathlib import Path
from datetime import datetime

CONFIG_FILE = "duality_config.json"

def load_or_create_config() -> dict:
    cfg_path = Path(__file__).resolve().parent.parent / CONFIG_FILE
    if cfg_path.exists():
        try:
            return json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    print("="*50)
    print("ПЕРВОНАЧАЛЬНАЯ НАСТРОЙКА")
    print("="*50)
    config = {}
    try:
        config['discord_client_id'] = input("Discord Client ID: ").strip()
        config['spotify_client_id'] = input("Spotify Client ID: ").strip()
        config['spotify_secret'] = input("Spotify Secret: ").strip()
    except KeyboardInterrupt:
        print("Настройка прервана пользователем"); sys.exit(0)

    if not all(config.values()):
        print("Ошибка: все поля обязательны"); sys.exit(1)

    cfg_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Конфигурация сохранена в {cfg_path.name}")
    return config
