import logging
import asyncio

from loader import dp, bot
from database.models import create_tables_safe
from mini_app.server import start_mini_app_server

# Routers
from handlers.start import router as start_router
from handlers.menu import router as menu_router
from handlers.tasks.router import router as tasks_router
from handlers.admin import router as admin_router
from handlers.profile import router as profile_router
from handlers.exchange_stars import router as exchange_router
from handlers.minigame import router as minigame_router
from handlers.topup import router as topup_router
from handlers.tasks.background_tasks import process_pending_rewards

logging.basicConfig(
    level=logging.INFO,
    filename="py_log.log",
    filemode='w',
    format="%(asctime)s %(levelname)s %(message)s"
)


async def main():
    """Initialize and run the bot."""
    logging.info("Запуск бота...")
    create_tables_safe()
    mini_app_runner = None

    # Register routers
    dp.include_router(start_router)
    dp.include_router(menu_router)
    dp.include_router(admin_router)
    dp.include_router(profile_router)
    dp.include_router(exchange_router)
    dp.include_router(minigame_router)
    dp.include_router(topup_router)
    dp.include_router(tasks_router)

    # Start background tasks
    asyncio.create_task(process_pending_rewards())

    try:
        mini_app_runner = await start_mini_app_server()
        await dp.start_polling(bot)
    finally:
        if mini_app_runner:
            await mini_app_runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
