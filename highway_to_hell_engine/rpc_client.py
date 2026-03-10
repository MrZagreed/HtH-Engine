import asyncio
import time
import traceback
from typing import Dict, Any
from pypresence import AioPresence, DiscordNotFound, InvalidID
from .logging_setup import log

RPC_TIMEOUT_S = 5.0
MAX_CONSECUTIVE_FAILURES = 8
RECONNECT_DELAYS = [1.0, 2.0, 5.0, 10.0, 30.0]  # Progressive reconnect delays

class RPCClient:
    """
    Enhanced RPC client with auto-recovery and detailed monitoring
    """
    def __init__(self, client_id: str):
        self.client_id = client_id
        self.rpc = AioPresence(client_id)
        self.connected = False
        self.connection_attempts = 0
        self.last_connection_attempt = 0
        self.stats = {
            'updates_sent': 0,
            'updates_failed': 0,
            'reconnects': 0,
            'last_success': 0,
            'last_error': None,
            'average_update_time': 0
        }
        self.rpc_lock = asyncio.Lock()
        self.error_state = {
            "fails": 0,
            "suspended": False,
            "suspend_time": 0,
            "last_error": None,
            "last_error_time": 0
        }

    async def connect(self, max_retries: int = 5) -> bool:
        """Connect to Discord RPC with retries"""
        if self.connected:
            return True

        for attempt in range(max_retries):
            self.connection_attempts += 1
            self.last_connection_attempt = time.time()
            
            try:
                log(f"Attempting Discord RPC connection ({attempt + 1}/{max_retries})...", "INFO", "rpc")
                await asyncio.wait_for(self.rpc.connect(), timeout=10.0)
                self.connected = True
                self.stats['reconnects'] += 1
                log("Discord RPC connected successfully", "INFO", "rpc")
                return True
                
            except asyncio.TimeoutError:
                log(f"Discord connection timeout (attempt {attempt + 1})", "WARNING", "rpc")
            except DiscordNotFound:
                log("Discord is not running or not found", "ERROR", "rpc")
                if attempt == max_retries - 1:
                    return False
            except InvalidID:
                log("Invalid Discord Client ID", "ERROR", "rpc")
                return False
            except Exception as e:
                log(f"Discord connection error: {e} (attempt {attempt + 1})", "ERROR", "rpc")
                self.stats['last_error'] = str(e)

            # Progressive delay between attempts
            delay = RECONNECT_DELAYS[min(attempt, len(RECONNECT_DELAYS) - 1)]
            log(f"Retrying in {delay} seconds...", "DEBUG", "rpc")
            await asyncio.sleep(delay)

        log("Failed to connect to Discord after all retries", "ERROR", "rpc")
        return False

    async def safe_update(self, payload: Dict[str, Any]) -> bool:
        """
        Safe RPC update with error handling and auto-recovery
        Returns True on successful update
        """
        start_time = time.time()
        
        # Check if updates are suspended
        if self.error_state.get("suspended", False):
            suspend_time = time.time() - self.error_state.get("suspend_time", 0)
            if suspend_time < 30:  # 30-second suspension window
                if int(suspend_time) % 10 == 0:  # Log every 10 seconds
                    log(f"RPC suspended, remaining {30 - int(suspend_time)}s", "WARNING", "rpc")
                return False
            else:
                # Attempt automatic recovery
                self.error_state["suspended"] = False
                self.error_state["fails"] = 0
                log("RPC auto-recovered after suspension", "INFO", "rpc")

        # Check connection state
        if not self.connected:
            log("RPC not connected, trying reconnect...", "WARNING", "rpc")
            if not await self.connect():
                return False

        try:
            async with self.rpc_lock:
                update_start = time.time()
                await asyncio.wait_for(self.rpc.update(**payload), timeout=RPC_TIMEOUT_S)
                update_time = time.time() - update_start

            # Successful update
            self.error_state["fails"] = 0
            self.error_state["suspended"] = False
            self.stats['last_success'] = time.time()
            self.stats['updates_sent'] += 1
            
            # Update average update time
            total_time = self.stats['average_update_time'] * (self.stats['updates_sent'] - 1)
            self.stats['average_update_time'] = (total_time + update_time) / self.stats['updates_sent']
            
            # Log slow updates
            if update_time > 1.0:
                log(f"Slow RPC update: {update_time:.2f}s", "DEBUG", "rpc")
                
            # Periodic stats
            if self.stats['updates_sent'] % 50 == 0:
                self._log_statistics()
                
            return True

        except asyncio.TimeoutError:
            self._handle_error("RPC update timeout")
            return False
            
        except ConnectionResetError:
            self._handle_error("RPC connection reset")
            await self._attempt_reconnect()
            return False
            
        except BrokenPipeError:
            self._handle_error("RPC pipe broken")
            await self._attempt_reconnect()
            return False
            
        except DiscordNotFound:
            self._handle_error("Discord not found")
            self.connected = False
            return False
            
        except Exception as e:
            self._handle_error(f"Unknown RPC error: {e}")
            log(traceback.format_exc(), "DEBUG", "rpc")
            await self._attempt_reconnect()
            return False

        finally:
            total_time = time.time() - start_time
            if total_time > 2.0:
                log(f"Long RPC update: {total_time:.2f}s", "WARNING", "rpc")

    def _handle_error(self, error_msg: str):
        """RPC error handler"""
        self.error_state["fails"] += 1
        self.error_state["last_error"] = error_msg
        self.error_state["last_error_time"] = time.time()
        self.stats['updates_failed'] += 1
        
        log(f"RPC error #{self.error_state['fails']}: {error_msg}", 
            "ERROR" if self.error_state["fails"] > 3 else "WARNING", "rpc")

        # Suspend updates after too many errors
        if self.error_state["fails"] >= MAX_CONSECUTIVE_FAILURES and not self.error_state["suspended"]:
            self.error_state["suspended"] = True
            self.error_state["suspend_time"] = time.time()
            log(f"RPC SUSPENDED: too many errors ({self.error_state['fails']})", "ERROR", "rpc")

    async def _attempt_reconnect(self):
        """Attempting RPC reconnect"""
        log("Attempting RPC reconnect...", "INFO", "rpc")
        try:
            await self.rpc.close()
            self.connected = False
            await asyncio.sleep(1.0)
            await self.connect()
        except Exception as e:
            log(f"RPC reconnect error: {e}", "ERROR", "rpc")

    async def clear_presence(self):
        """Clear RPC presence"""
        try:
            async with self.rpc_lock:
                await self.rpc.clear()
            log("RPC presence cleared", "INFO", "rpc")
        except Exception as e:
            log(f"RPC clear error: {e}", "ERROR", "rpc")

    async def close(self):
        """Close RPC connection"""
        try:
            await self.clear_presence()
            await self.rpc.close()
            self.connected = False
            log("RPC connection closed", "INFO", "rpc")
        except Exception as e:
            log(f"RPC close error: {e}", "ERROR", "rpc")

    def _log_statistics(self):
        """RPC stats logging"""
        success_rate = (self.stats['updates_sent'] / 
                       max(1, self.stats['updates_sent'] + self.stats['updates_failed'])) * 100
        
        log(f"RPC STATS: sent={self.stats['updates_sent']}, "
            f"failed={self.stats['updates_failed']}, "
            f"success={success_rate:.1f}%, "
            f"avg_time={self.stats['average_update_time']:.3f}s, "
            f"reconnects={self.stats['reconnects']}", "INFO", "rpc")

    def get_status(self) -> Dict[str, Any]:
        """Get current RPC client status"""
        return {
            'connected': self.connected,
            'connection_attempts': self.connection_attempts,
            'last_connection_attempt': self.last_connection_attempt,
            'error_state': self.error_state.copy(),
            'stats': self.stats.copy(),
            'suspended': self.error_state.get("suspended", False),
            'suspended_until': self.error_state.get("suspend_time", 0) + 30 if self.error_state.get("suspended") else 0
        }


# Legacy compatibility
async def safe_rpc_update(rpc: AioPresence, payload: Dict[str, Any], rpc_lock: asyncio.Lock, error_state: Dict[str, Any]) -> bool:
    """
    Legacy-compatible function
    Returns True if update succeeded
    """
    # Create temporary compatibility client
    temp_client = RPCClient("temp")
    temp_client.rpc = rpc
    temp_client.connected = True
    temp_client.rpc_lock = rpc_lock
    temp_client.error_state = error_state
    
    return await temp_client.safe_update(payload)


async def emergency_clear_rpc(rpc: AioPresence):
    """Emergency RPC cleanup"""
    try:
        await rpc.clear()
        await rpc.close()
        log("Emergency RPC cleanup completed", "INFO", "rpc")
    except Exception as e:
        log(f"Emergency RPC cleanup failed: {e}", "ERROR", "rpc")


__all__ = ["RPCClient", "safe_rpc_update", "emergency_clear_rpc"]
