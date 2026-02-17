from pathlib import Path
import logging
import random

from aiohttp import web

from config import MINI_APP_HOST, MINI_APP_PORT
from database.models import User

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"


async def index(_: web.Request) -> web.FileResponse:
    return web.FileResponse(STATIC_DIR / "index.html")


async def user_balance(request: web.Request) -> web.Response:
    user_id_raw = request.query.get("user_id")
    if not user_id_raw or not user_id_raw.isdigit():
        return web.json_response({"ok": False, "error": "invalid_user_id"}, status=400)

    user = User.get_or_none(User.user_id == int(user_id_raw))
    balance = int(user.balance) if user else 0

    return web.json_response({"ok": True, "balance": balance})


GAMES = {
    "dice": {
        "name": "Кубик",
        "roll": lambda: random.randint(1, 6),
        "is_win": lambda value: value >= 5,
        "reward": 12,
    },
    "basketball": {
        "name": "Баскетбол",
        "roll": lambda: random.randint(1, 5),
        "is_win": lambda value: value >= 4,
        "reward": 10,
    },
}


async def play_game(request: web.Request) -> web.Response:
    payload = await request.json()

    user_id_raw = str(payload.get("user_id", ""))
    game_key = str(payload.get("game", ""))

    if not user_id_raw.isdigit() or game_key not in GAMES:
        return web.json_response({"ok": False, "error": "invalid_payload"}, status=400)

    user_id = int(user_id_raw)
    game = GAMES[game_key]

    if not User.update(balance=User.balance - 5).where(
        (User.user_id == user_id) & (User.balance >= 5)
    ).execute():
        user = User.get_or_none(User.user_id == user_id)
        balance = int(user.balance) if user else 0
        return web.json_response(
            {
                "ok": False,
                "error": "not_enough_balance",
                "balance": balance,
            },
            status=400,
        )

    value = game["roll"]()
    won = game["is_win"](value)
    reward = game["reward"] if won else 0

    if reward:
        User.update(balance=User.balance + reward).where(User.user_id == user_id).execute()

    user = User.get_or_none(User.user_id == user_id)
    balance = int(user.balance) if user else 0

    return web.json_response(
        {
            "ok": True,
            "game": game_key,
            "game_name": game["name"],
            "value": value,
            "won": won,
            "reward": reward,
            "balance": balance,
            "stake": 5,
        }
    )


def create_mini_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/api/user-balance", user_balance)
    app.router.add_post("/api/play", play_game)
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
