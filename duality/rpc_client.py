import asyncio
import time
import traceback
from typing import Dict, Any
from pypresence import AioPresence, DiscordNotFound, InvalidID
from .logging_setup import log

RPC_TIMEOUT_S = 5.0
MAX_CONSECUTIVE_FAILURES = 8
RECONNECT_DELAYS = [1.0, 2.0, 5.0, 10.0, 30.0]  # Прогрессивные задержки переподключения

class RPCClient:
    """
    Улучшенный RPC клиент с автоматическим восстановлением и детальным мониторингом
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
        """Подключение к Discord RPC с повторными попытками"""
        if self.connected:
            return True

        for attempt in range(max_retries):
            self.connection_attempts += 1
            self.last_connection_attempt = time.time()
            
            try:
                log(f"Попытка подключения к Discord RPC ({attempt + 1}/{max_retries})...", "INFO", "rpc")
                await asyncio.wait_for(self.rpc.connect(), timeout=10.0)
                self.connected = True
                self.stats['reconnects'] += 1
                log("✓ Успешное подключение к Discord RPC", "INFO", "rpc")
                return True
                
            except asyncio.TimeoutError:
                log(f"Таймаут подключения к Discord (попытка {attempt + 1})", "WARNING", "rpc")
            except DiscordNotFound:
                log("Discord не запущен или не найден", "ERROR", "rpc")
                if attempt == max_retries - 1:
                    return False
            except InvalidID:
                log("Неверный Client ID Discord", "ERROR", "rpc")
                return False
            except Exception as e:
                log(f"Ошибка подключения к Discord: {e} (попытка {attempt + 1})", "ERROR", "rpc")
                self.stats['last_error'] = str(e)

            # Прогрессивная задержка между попытками
            delay = RECONNECT_DELAYS[min(attempt, len(RECONNECT_DELAYS) - 1)]
            log(f"Повторная попытка через {delay} секунд...", "DEBUG", "rpc")
            await asyncio.sleep(delay)

        log("Не удалось подключиться к Discord после всех попыток", "ERROR", "rpc")
        return False

    async def safe_update(self, payload: Dict[str, Any]) -> bool:
        """
        Безопасное обновление RPC с обработкой ошибок и автоматическим восстановлением
        Возвращает True при успешном обновлении
        """
        start_time = time.time()
        
        # Проверяем не приостановлены ли обновления
        if self.error_state.get("suspended", False):
            suspend_time = time.time() - self.error_state.get("suspend_time", 0)
            if suspend_time < 30:  # 30 секунд приостановки
                if int(suspend_time) % 10 == 0:  # Логируем каждые 10 секунд
                    log(f"RPC приостановлен, осталось {30 - int(suspend_time)}с", "WARNING", "rpc")
                return False
            else:
                # Пробуем восстановить работу
                self.error_state["suspended"] = False
                self.error_state["fails"] = 0
                log("Автоматическое восстановление RPC после приостановки", "INFO", "rpc")

        # Проверяем подключение
        if not self.connected:
            log("RPC не подключен, попытка переподключения...", "WARNING", "rpc")
            if not await self.connect():
                return False

        try:
            async with self.rpc_lock:
                update_start = time.time()
                await asyncio.wait_for(self.rpc.update(**payload), timeout=RPC_TIMEOUT_S)
                update_time = time.time() - update_start

            # Успешное обновление
            self.error_state["fails"] = 0
            self.error_state["suspended"] = False
            self.stats['last_success'] = time.time()
            self.stats['updates_sent'] += 1
            
            # Обновляем среднее время обновления
            total_time = self.stats['average_update_time'] * (self.stats['updates_sent'] - 1)
            self.stats['average_update_time'] = (total_time + update_time) / self.stats['updates_sent']
            
            # Логируем медленные обновления
            if update_time > 1.0:
                log(f"Медленное обновление RPC: {update_time:.2f}с", "DEBUG", "rpc")
                
            # Периодическая статистика
            if self.stats['updates_sent'] % 50 == 0:
                self._log_statistics()
                
            return True

        except asyncio.TimeoutError:
            self._handle_error("Таймаут обновления RPC")
            return False
            
        except ConnectionResetError:
            self._handle_error("Сброс соединения RPC")
            await self._attempt_reconnect()
            return False
            
        except BrokenPipeError:
            self._handle_error("Обрыв канала RPC")
            await self._attempt_reconnect()
            return False
            
        except DiscordNotFound:
            self._handle_error("Discord не найден")
            self.connected = False
            return False
            
        except Exception as e:
            self._handle_error(f"Неизвестная ошибка RPC: {e}")
            log(traceback.format_exc(), "DEBUG", "rpc")
            await self._attempt_reconnect()
            return False

        finally:
            total_time = time.time() - start_time
            if total_time > 2.0:
                log(f"Долгое обновление RPC: {total_time:.2f}с", "WARNING", "rpc")

    def _handle_error(self, error_msg: str):
        """Обработка ошибки RPC"""
        self.error_state["fails"] += 1
        self.error_state["last_error"] = error_msg
        self.error_state["last_error_time"] = time.time()
        self.stats['updates_failed'] += 1
        
        log(f"Ошибка RPC #{self.error_state['fails']}: {error_msg}", 
            "ERROR" if self.error_state["fails"] > 3 else "WARNING", "rpc")

        # Приостанавливаем обновления после множества ошибок
        if self.error_state["fails"] >= MAX_CONSECUTIVE_FAILURES and not self.error_state["suspended"]:
            self.error_state["suspended"] = True
            self.error_state["suspend_time"] = time.time()
            log(f"ПРИОСТАНОВКА RPC: слишком много ошибок ({self.error_state['fails']})", "ERROR", "rpc")

    async def _attempt_reconnect(self):
        """Попытка переподключения к RPC"""
        log("Попытка переподключения к RPC...", "INFO", "rpc")
        try:
            await self.rpc.close()
            self.connected = False
            await asyncio.sleep(1.0)
            await self.connect()
        except Exception as e:
            log(f"Ошибка переподключения RPC: {e}", "ERROR", "rpc")

    async def clear_presence(self):
        """Очистка RPC присутствия"""
        try:
            async with self.rpc_lock:
                await self.rpc.clear()
            log("RPC присутствие очищено", "INFO", "rpc")
        except Exception as e:
            log(f"Ошибка очистки RPC: {e}", "ERROR", "rpc")

    async def close(self):
        """Закрытие RPC соединения"""
        try:
            await self.clear_presence()
            await self.rpc.close()
            self.connected = False
            log("RPC соединение закрыто", "INFO", "rpc")
        except Exception as e:
            log(f"Ошибка закрытия RPC: {e}", "ERROR", "rpc")

    def _log_statistics(self):
        """Логирование статистики RPC"""
        success_rate = (self.stats['updates_sent'] / 
                       max(1, self.stats['updates_sent'] + self.stats['updates_failed'])) * 100
        
        log(f"СТАТИСТИКА RPC: отправлено={self.stats['updates_sent']}, "
            f"ошибок={self.stats['updates_failed']}, "
            f"успех={success_rate:.1f}%, "
            f"среднее_время={self.stats['average_update_time']:.3f}с, "
            f"переподключений={self.stats['reconnects']}", "INFO", "rpc")

    def get_status(self) -> Dict[str, Any]:
        """Получение текущего статуса RPC клиента"""
        return {
            'connected': self.connected,
            'connection_attempts': self.connection_attempts,
            'last_connection_attempt': self.last_connection_attempt,
            'error_state': self.error_state.copy(),
            'stats': self.stats.copy(),
            'suspended': self.error_state.get("suspended", False),
            'suspended_until': self.error_state.get("suspend_time", 0) + 30 if self.error_state.get("suspended") else 0
        }


# Совместимость со старым кодом
async def safe_rpc_update(rpc: AioPresence, payload: Dict[str, Any], rpc_lock: asyncio.Lock, error_state: Dict[str, Any]) -> bool:
    """
    Совместимая функция для старого кода
    Возвращает True если обновление успешно
    """
    # Создаем временный клиент для совместимости
    temp_client = RPCClient("temp")
    temp_client.rpc = rpc
    temp_client.connected = True
    temp_client.rpc_lock = rpc_lock
    temp_client.error_state = error_state
    
    return await temp_client.safe_update(payload)


async def emergency_clear_rpc(rpc: AioPresence):
    """Аварийная очистка RPC"""
    try:
        await rpc.clear()
        await rpc.close()
        log("Аварийная очистка RPC выполнена", "INFO", "rpc")
    except Exception as e:
        log(f"Аварийная очистка RPC не удалась: {e}", "ERROR", "rpc")


__all__ = ["RPCClient", "safe_rpc_update", "emergency_clear_rpc"]