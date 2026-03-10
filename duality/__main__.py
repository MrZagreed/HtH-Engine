import asyncio
import argparse
import sys
from .config import load_or_create_config
from .main import main

if __name__ == "__main__":
    # Для Windows RPC в pypresence требуется Proactor loop (pipe transport).
    if sys.platform == "win32" and hasattr(asyncio, "WindowsProactorEventLoopPolicy"):
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['api', 'local'], default='api',
                        help='Режим получения данных: api (требуется Premium) или local (без Premium)')
    args = parser.parse_args()

    cfg = load_or_create_config(mode=args.mode)
    asyncio.run(main(cfg, mode=args.mode))
