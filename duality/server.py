import ssl
from aiohttp import web
from .logging_setup import log

class LocalHttpsServer:
    def __init__(self, port=8888):
        self.port=port
        self.app = web.Application()
        self.runner = None
        self.site = None
        self.ssl_context = None

    def setup_ssl(self):
        try:
            self.ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            self.ssl_context.check_hostname = False
            self.ssl_context.verify_mode = ssl.CERT_NONE
            log("SSL контекст создан (dev)", "INFO", "server")
        except Exception as e:
            log(f"Ошибка SSL: {e}", "WARNING", "server")
            self.ssl_context = None

    async def handle_callback(self, request):
        log(f"Callback: {request.query_string}", "INFO", "server")
        return web.Response(text="Аутентификация успешна! Можно закрыть вкладку.")

    async def start(self):
        self.setup_ssl()
        self.app.router.add_get("/callback", self.handle_callback)
        self.runner = web.AppRunner(self.app); await self.runner.setup()
        self.site = web.TCPSite(self.runner, '127.0.0.1', self.port, ssl_context=self.ssl_context)
        await self.site.start()
        log(f"HTTPS сервер: https://127.0.0.1:{self.port}/callback", "INFO", "server")
        return f"https://127.0.0.1:{self.port}/callback"

    async def stop(self):
        if self.site: await self.site.stop()
        if self.runner: await self.runner.cleanup()
        log("HTTPS сервер остановлен", "INFO", "server")

__all__ = ["LocalHttpsServer"]
