import socket
import time
from typing import Dict, Any, List, Optional, Tuple

from .logging_setup import log


class NetworkMonitor:
    """Connectivity monitor with latency tracking and outage diagnostics."""

    def __init__(self):
        self.last_net_ok = time.time()
        self.consecutive_failures = 0
        self.total_checks = 0
        self.total_failures = 0
        self.latency_history: List[float] = []

        self.state = "unknown"  # unknown | online | degraded | offline
        self.last_state_change = time.time()
        self.last_error: Optional[str] = None
        self.last_latency_ms = 0.0
        self.outage_started_at: Optional[float] = None

    def _set_state(self, new_state: str, reason: str) -> None:
        if new_state == self.state:
            return
        old_state = self.state
        self.state = new_state
        self.last_state_change = time.time()
        log(f"NETWORK | state {old_state} -> {new_state} ({reason})", "INFO", "network")

    def check(self, host: str = "8.8.8.8", port: int = 53, timeout: float = 0.7) -> bool:
        """Legacy-compatible bool check."""
        ok, _, _ = self.check_with_latency(host=host, port=port, timeout=timeout)
        return ok

    def check_with_latency(
        self,
        host: str = "8.8.8.8",
        port: int = 53,
        timeout: float = 1.0,
    ) -> Tuple[bool, float, Optional[str]]:
        """Extended check with latency and failure details."""
        self.total_checks += 1
        start_time = time.time()

        try:
            sock = socket.create_connection((host, port), timeout=timeout)
            sock.close()
            latency = (time.time() - start_time) * 1000.0
            self.last_latency_ms = latency
            self.last_error = None

            if self.consecutive_failures:
                downtime = 0.0
                if self.outage_started_at is not None:
                    downtime = time.time() - self.outage_started_at
                log(
                    f"NETWORK | restored after {self.consecutive_failures} failures "
                    f"(downtime {downtime:.1f}s, latency {latency:.1f}ms)",
                    "INFO",
                    "network",
                )

            self.consecutive_failures = 0
            self.last_net_ok = time.time()
            self.latency_history.append(latency)
            if len(self.latency_history) > 120:
                self.latency_history.pop(0)

            if latency >= 350.0:
                self._set_state("degraded", f"high latency {latency:.1f}ms")
            else:
                self._set_state("online", f"latency {latency:.1f}ms")

            self.outage_started_at = None
            return True, latency, None

        except Exception as e:
            self.consecutive_failures += 1
            self.total_failures += 1
            self.last_error = str(e)

            if self.outage_started_at is None:
                self.outage_started_at = time.time()
            outage_for = time.time() - self.outage_started_at

            self._set_state("offline", f"{type(e).__name__}")
            lvl = "WARNING" if self.consecutive_failures < 5 else "ERROR"
            log(
                f"NETWORK | failure #{self.consecutive_failures}: {e} "
                f"(outage {outage_for:.1f}s)",
                lvl,
                "network",
            )
            return False, -1.0, str(e)

    def stats(self) -> Dict[str, Any]:
        ok = self.total_checks - self.total_failures
        return {
            "state": self.state,
            "last_net_ok": self.last_net_ok,
            "last_state_change": self.last_state_change,
            "consecutive_failures": self.consecutive_failures,
            "total_checks": self.total_checks,
            "total_failures": self.total_failures,
            "success_rate": ok / max(1, self.total_checks) * 100.0,
            "last_error": self.last_error,
            "last_latency_ms": self.last_latency_ms,
            "outage_seconds": 0.0 if self.outage_started_at is None else time.time() - self.outage_started_at,
        }

    def get_latency_stats(self) -> Dict[str, float]:
        if not self.latency_history:
            return {"avg": 0.0, "min": 0.0, "max": 0.0, "last": 0.0}

        return {
            "avg": sum(self.latency_history) / len(self.latency_history),
            "min": min(self.latency_history),
            "max": max(self.latency_history),
            "last": self.latency_history[-1],
        }

    def diagnostics_snapshot(self) -> Dict[str, Any]:
        data = self.stats()
        data["latency"] = self.get_latency_stats()
        return data


class NetworkLatencyPredictor:
    def __init__(self, window_size: int = 50):
        self.window_size = window_size
        self.history: List[float] = []
        self.last_pred = 50.0

    def add(self, rtt_ms: float) -> None:
        self.history.append(rtt_ms)
        if len(self.history) > self.window_size:
            self.history.pop(0)

    def predict(self) -> Dict[str, float]:
        if not self.history:
            return {"predicted_rtt": 50.0, "confidence": 0.1}
        avg = sum(self.history[-10:]) / min(10, len(self.history))
        self.last_pred = max(10.0, min(500.0, avg))
        conf = min(0.95, 0.2 + 0.05 * len(self.history))
        return {"predicted_rtt": self.last_pred, "confidence": conf}


__all__ = ["NetworkMonitor", "NetworkLatencyPredictor"]
