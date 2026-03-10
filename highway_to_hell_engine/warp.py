import time
from collections import deque
from .logging_setup import log

class TimeWarp:
    def __init__(self, max_drift_ms: int = 5000, aggressive_correction: bool = True):
        self.max_drift = int(max_drift_ms)
        self.aggressive = aggressive_correction

        self.offset = 0.0
        self.last_reported = None
        self.last_corrected = 0

        self.total_corrections = 0
        self.drift_history = deque(maxlen=120)
        self.last_log_time = 0.0

    def reset(self):
        self.offset = 0.0
        self.last_reported = None
        self.last_corrected = 0
        self.total_corrections = 0
        self.drift_history.clear()
        self.last_log_time = 0.0

    def update(self, reported_ms: int, shown_ms: int, now: float | None = None) -> int:
        if now is None:
            now = time.time()
        reported_ms = int(max(0, reported_ms))
        shown_ms = int(max(0, shown_ms))

        if self.last_reported is None:
            self.offset = float(reported_ms - shown_ms)
            corrected = reported_ms - int(round(self.offset))
            self.last_reported = reported_ms
            self.last_corrected = max(0, corrected)
            self.total_corrections += 1
            self._maybe_log(now, reported_ms, shown_ms, corrected)
            return self.last_corrected

        error = reported_ms - shown_ms
        abs_err = abs(error)

        if abs_err > 5000:
            self.offset = 0.0
            corrected = reported_ms
        else:
            if self.aggressive:
                alpha = 0.16 if abs_err > 2500 else (0.08 if abs_err > 800 else 0.04)
            else:
                alpha = 0.04
            self.offset = (1.0 - alpha) * self.offset + alpha * error
            if self.offset > self.max_drift:
                self.offset = float(self.max_drift)
            if self.offset < -self.max_drift:
                self.offset = float(-self.max_drift)
            corrected = reported_ms - int(round(self.offset))

        if corrected + 5 < self.last_corrected and abs_err < 2500:
            corrected = self.last_corrected + 1

        self.last_reported = reported_ms
        self.last_corrected = max(0, corrected)
        self.total_corrections += 1
        self.drift_history.append(error)
        self._maybe_log(now, reported_ms, shown_ms, self.last_corrected, error)
        return self.last_corrected

    def _maybe_log(self, now: float, reported_ms: int, shown_ms: int, corrected_ms: int, error: int | None = None):
        if error is None:
            error = reported_ms - shown_ms
        # Log less often: every 30s or every 100 corrections
        log_every = 30.0
        if (now - self.last_log_time) >= log_every or self.total_corrections % 100 == 0 or abs(error) > 5000:
            avg = sum(self.drift_history)/len(self.drift_history) if self.drift_history else 0.0
            log(
                f"SYNC: reported={reported_ms}ms, shown={shown_ms}ms, "
                f"drift={error}ms, corrected={corrected_ms}ms, "
                f"avg_drift={avg:.1f}ms, corrections={self.total_corrections}",
                "INFO", "warp"
            )
            self.last_log_time = now

__all__ = ["TimeWarp"]