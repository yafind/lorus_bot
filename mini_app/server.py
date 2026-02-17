from pathlib import Path
import logging

from aiohttp import web

from config import MINI_APP_HOST, MINI_APP_PORT, MINI_APP_URL, payment_chat
from database.models import User

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"


async def index(_: web.Request) -> web.FileResponse:
    return web.FileResponse(STATIC_DIR / "index.html")


async def app_config(_: web.Request) -> web.Response:
    return web.json_response(
        {
            "mini_app_url": MINI_APP_URL,
            "payment_chat": payment_chat,
        }
    )


async def user_balance(request: web.Request) -> web.Response:
    user_id_raw = request.query.get("user_id")
    if not user_id_raw or not user_id_raw.isdigit():
        return web.json_response({"ok": False, "error": "invalid_user_id"}, status=400)

    user = User.get_or_none(User.user_id == int(user_id_raw))
    balance = int(user.balance) if user else 0

    return web.json_response({"ok": True, "balance": balance})


def create_mini_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/api/config", app_config)
    app.router.add_get("/api/user-balance", user_balance)
    app.router.add_static("/static/", path=STATIC_DIR, show_index=False)
    return app


async def start_mini_app_server() -> web.AppRunner:
    app = create_mini_app()
    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, host=MINI_APP_HOST, port=MINI_APP_PORT)
    await site.start()

    logger.info("Mini App server started on %s:%s", MINI_APP_HOST, MINI_APP_PORT)
    return runner
