import logging
import os
import re
from datetime import datetime
from pathlib import Path

try:
    from colorama import init as color_init, Fore, Style
    color_init()
    _COLORS = True
except ImportError:
    _COLORS = False

    class Fore:
        RED = GREEN = YELLOW = BLUE = CYAN = MAGENTA = WHITE = RESET = ""

    class Style:
        RESET_ALL = ""

    _missing_colorama = True
else:
    _missing_colorama = False

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

_LOG_RE = re.compile(r"^(debug|highway_to_hell_engine)_(\d{8}_\d{6})\.log$")


def cleanup_old_logs(max_sessions: int = 5) -> None:
    """
    Keeps only the latest `max_sessions` runs.
    One run = 2 files (debug_* and highway_to_hell_engine_*).
    """
    try:
        log_files = list(LOG_DIR.glob("*.log"))
        sessions = {}
        extra_files = []

        for path in log_files:
            m = _LOG_RE.match(path.name)
            if not m:
                extra_files.append(path)
                continue
            ts = m.group(2)
            sessions.setdefault(ts, []).append(path)

        keep_ts = set(sorted(sessions.keys(), reverse=True)[:max_sessions])
        to_delete = []

        for ts, files in sessions.items():
            if ts not in keep_ts:
                to_delete.extend(files)

        # Keep only last 10 nonstandard log files.
        extra_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        to_delete.extend(extra_files[10:])

        for old in to_delete:
            try:
                old.unlink(missing_ok=True)
            except Exception:
                # If file is locked by another process, continue cleanup.
                continue
    except Exception:
        # Log cleanup must never crash the app.
        pass


cleanup_old_logs(5)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_FILE = LOG_DIR / f"highway_to_hell_engine_{timestamp}.log"
DEBUG_LOG_FILE = LOG_DIR / f"debug_{timestamp}.log"


class AdvancedLogger:
    def __init__(self, level: str = "INFO"):
        self.logger = logging.getLogger("highway_to_hell_engine")
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

        if _missing_colorama:
            self.log("WARNING", "colorama is not installed - console colors disabled.", "logging")

    def log(self, level: str, msg: str, component: str = "main"):
        getattr(self.logger, level.lower())(msg)


LOGGER = AdvancedLogger(level=os.environ.get("HIGHWAY_TO_HELL_ENGINE_LOG_LEVEL", "INFO"))


def log(msg: str, level: str = "INFO", component: str = "main"):
    LOGGER.log(level, msg)


__all__ = ["log", "LOGGER", "LOG_FILE", "DEBUG_LOG_FILE"]
