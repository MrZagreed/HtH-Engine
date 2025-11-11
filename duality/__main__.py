import asyncio
from .config import load_or_create_config
from .main import main

if __name__ == "__main__":
    cfg = load_or_create_config()
    asyncio.run(main(cfg))
