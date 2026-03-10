import asyncio
import argparse
import sys
from .config import load_or_create_config
from .main import main

if __name__ == "__main__":
    if sys.platform == "win32" and hasattr(asyncio, "WindowsProactorEventLoopPolicy"):
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=["api", "local"],
        default="api",
        help="Data source mode: api (requires Premium) or local (no Premium required)",
    )
    parser.add_argument(
        "--lang",
        choices=["en", "ru"],
        default="en",
        help="Wizard language: en or ru",
    )
    args = parser.parse_args()

    cfg = load_or_create_config(mode=args.mode, lang=args.lang)
    asyncio.run(main(cfg, mode=args.mode))
