import socket, time, json
from typing import Dict, Any, List
from .logging_setup import log

class NetworkMonitor:
    def __init__(self):
        self.last_net_ok = time.time()
        self.consecutive_failures = 0
        self.total_checks = 0
        self.total_failures = 0
        self.latency_history = []
        
    def check(self, host="8.8.8.8", port=53, timeout=0.7) -> bool:
        """Main network check method (legacy-compatible)"""
        self.total_checks += 1
        try:
            sock = socket.create_connection((host, port), timeout=timeout)
            sock.close()
            if self.consecutive_failures:
                log(f"NETWORK | restored after {self.consecutive_failures} failures", "INFO", "network")
            self.consecutive_failures = 0
            self.last_net_ok = time.time()
            return True
        except Exception as e:
            self.consecutive_failures += 1
            self.total_failures += 1
            lvl = "WARNING" if self.consecutive_failures < 5 else "ERROR"
            log(f"NETWORK | failure #{self.consecutive_failures}: {e}", lvl, "network")
            return False

    def check_with_latency(self, host="8.8.8.8", port=53, timeout=1.0) -> tuple:
        """Extended check with latency measurement"""
        self.total_checks += 1
        start_time = time.time()
        try:
            sock = socket.create_connection((host, port), timeout=timeout)
            sock.close()
            latency = (time.time() - start_time) * 1000
            
            if self.consecutive_failures:
                log(f"NETWORK | restored after {self.consecutive_failures} failures, latency={latency:.1f}ms", "INFO", "network")
            
            self.consecutive_failures = 0
            self.last_net_ok = time.time()
            self.latency_history.append(latency)
            if len(self.latency_history) > 50:
                self.latency_history.pop(0)
                
            return True, latency
        except Exception as e:
            self.consecutive_failures += 1
            self.total_failures += 1
            latency = -1
            
            lvl = "WARNING" if self.consecutive_failures < 5 else "ERROR"
            log(f"NETWORK | failure #{self.consecutive_failures}: {e}", lvl, "network")
            return False, latency

    def stats(self) -> Dict[str, Any]:
        ok = self.total_checks - self.total_failures
        return dict(
            last_net_ok=self.last_net_ok,
            consecutive_failures=self.consecutive_failures,
            total_checks=self.total_checks,
            total_failures=self.total_failures,
            success_rate=ok / max(1, self.total_checks) * 100
        )

    def get_latency_stats(self) -> dict:
        if not self.latency_history:
            return {"avg": 0, "min": 0, "max": 0, "last": 0}
        
        return {
            "avg": sum(self.latency_history) / len(self.latency_history),
            "min": min(self.latency_history),
            "max": max(self.latency_history),
            "last": self.latency_history[-1] if self.latency_history else 0
        }

class NetworkLatencyPredictor:
    def __init__(self, window_size=50):
        self.window_size = window_size
        self.history: List[float] = []
        self.last_pred = 50.0

    def add(self, rtt_ms: float):
        self.history.append(rtt_ms)
        if len(self.history) > self.window_size:
            self.history.pop(0)

    def predict(self) -> Dict[str, float]:
        if not self.history: 
            return dict(predicted_rtt=50.0, confidence=0.1)
        avg = sum(self.history[-10:]) / min(10, len(self.history))
        self.last_pred = max(10.0, min(500.0, avg))
        conf = min(0.95, 0.2 + 0.05 * len(self.history))
        return dict(predicted_rtt=self.last_pred, confidence=conf)

__all__ = ["NetworkMonitor", "NetworkLatencyPredictor"]