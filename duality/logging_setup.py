import logging
import os
import sys
from datetime import datetime
from pathlib import Path
import glob

try:
    from colorama import init as color_init, Fore, Style
    color_init()
    _COLORS = True
except ImportError:
    _COLORS = False
    # Заглушки для цветов
    class Fore:
        RED=GREEN=YELLOW=BLUE=CYAN=MAGENTA=WHITE=RESET=""
    class Style:
        RESET_ALL=""
    # Логируем отсутствие colorama, но позже, когда логгер уже создан
    _missing_colorama = True
else:
    _missing_colorama = False

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

def cleanup_old_logs(max_logs: int = 5):
    try:
        log_files = list(LOG_DIR.glob("*.log"))
        log_files.sort(key=lambda x: x.stat().st_mtime)
        while len(log_files) > max_logs:
            old = log_files.pop(0)
            old.unlink(missing_ok=True)
    except Exception:
        pass

cleanup_old_logs(5)

timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
LOG_FILE = LOG_DIR / f"duality_{timestamp}.log"
DEBUG_LOG_FILE = LOG_DIR / f"debug_{timestamp}.log"

class AdvancedLogger:
    def __init__(self, level: str = "INFO"):
        self.logger = logging.getLogger("duality")
        self.logger.setLevel(logging.DEBUG)

        fmt = logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s", datefmt="%H:%M:%S")

        fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)

        dh = logging.FileHandler(DEBUG_LOG_FILE, encoding="utf-8")
        dh.setLevel(logging.DEBUG)
        dh.setFormatter(fmt)

        ch = logging.StreamHandler()
        ch.setLevel(getattr(logging, level.upper(), logging.INFO))

        class ColorFormatter(logging.Formatter):
            def format(self, record):
                msg = super().format(record)
                if not _COLORS:
                    return msg
                if record.levelno >= logging.ERROR:
                    return Fore.RED + msg + Style.RESET_ALL
                if record.levelno >= logging.WARNING:
                    return Fore.YELLOW + msg + Style.RESET_ALL
                if record.levelno >= logging.INFO:
                    return Fore.CYAN + msg + Style.RESET_ALL
                return Fore.WHITE + msg + Style.RESET_ALL

        ch.setFormatter(ColorFormatter("%(message)s"))

        self.logger.handlers.clear()
        self.logger.addHandler(fh)
        self.logger.addHandler(dh)
        self.logger.addHandler(ch)

        # Если colorama отсутствует, логируем предупреждение (после инициализации логгера)
        if _missing_colorama:
            self.log("colorama не установлен — цвета в консоли отключены.", "WARNING", "logging")

    def log(self, level: str, msg: str, component: str = "main"):
        getattr(self.logger, level.lower())(msg)

LOGGER = AdvancedLogger(level=os.environ.get("DUALITY_LOG_LEVEL", "INFO"))

def log(msg: str, level: str = "INFO", component: str = "main"):
    LOGGER.log(level, msg)

__all__ = ["log", "LOGGER", "LOG_FILE", "DEBUG_LOG_FILE"]