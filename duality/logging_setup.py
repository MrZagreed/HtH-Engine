import logging, os, sys, time
from datetime import datetime
from pathlib import Path

try:
    from colorama import init as color_init, Fore, Style
    color_init()
    _COLORS = True
except Exception:
    _COLORS = False
    class Fore:
        RED=GREEN=YELLOW=BLUE=CYAN=MAGENTA=WHITE=RESET=""
    class Style:
        RESET_ALL=""

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / f"duality_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
DEBUG_LOG_FILE = LOG_DIR / f"debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

class AdvancedLogger:
    def __init__(self, level: str = "INFO"):
        self.logger = logging.getLogger("duality")
        self.logger.setLevel(logging.DEBUG)

        fmt = logging.Formatter("%(asctime)s.%(msecs)03d | %(levelname)-8s | [%(name)s] %(message)s", datefmt="%H:%M:%S")

        fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
        fh.setLevel(logging.DEBUG); fh.setFormatter(fmt)

        dh = logging.FileHandler(DEBUG_LOG_FILE, encoding="utf-8")
        dh.setLevel(logging.DEBUG); dh.setFormatter(fmt)

        ch = logging.StreamHandler()
        ch.setLevel(getattr(logging, level.upper(), logging.INFO))

        class ColorFormatter(logging.Formatter):
            def format(self, record):
                msg = super().format(record)
                if not _COLORS: return msg
                if record.levelno >= logging.ERROR:
                    return Fore.RED + msg + Style.RESET_ALL
                if record.levelno >= logging.WARNING:
                    return Fore.YELLOW + msg + Style.RESET_ALL
                if record.levelno >= logging.INFO:
                    return Fore.CYAN + msg + Style.RESET_ALL
                return Fore.WHITE + msg + Style.RESET_ALL

        ch.setFormatter(ColorFormatter("%(asctime)s.%(msecs)03d | %(levelname)-8s | [%(name)s] %(message)s", datefmt="%H:%M:%S"))
        self.logger.addHandler(fh); self.logger.addHandler(dh); self.logger.addHandler(ch)

        self.spotify = logging.getLogger("duality.spotify")
        self.rpc     = logging.getLogger("duality.rpc")
        self.lyrics  = logging.getLogger("duality.lyrics")
        self.sync    = logging.getLogger("duality.sync")
        self.network = logging.getLogger("duality.network")
        self.tempo   = logging.getLogger("duality.tempo")
        for l in (self.spotify, self.rpc, self.lyrics, self.sync, self.network, self.tempo):
            l.setLevel(logging.DEBUG)
            for h in (fh, dh, ch): l.addHandler(h)

    def log(self, level: str, msg: str, component: str = "main"):
        getattr(self.logger, level.lower())(f"[{component.upper():8}] {msg}")

LOGGER = AdvancedLogger(level=os.environ.get("DUALITY_LOG_LEVEL", "INFO"))
def log(msg: str, level: str = "INFO", component: str = "main"): LOGGER.log(level, msg, component)

__all__ = ["log", "LOGGER", "LOG_FILE", "DEBUG_LOG_FILE"]
