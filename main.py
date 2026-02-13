import logging
import asyncio

from loader import dp, bot
from database.models import create_tables_safe

# Routers
from handlers.start import router as start_router
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

    # Register routers
    dp.include_router(start_router)
    dp.include_router(admin_router)
    dp.include_router(profile_router)
    dp.include_router(exchange_router)
    dp.include_router(minigame_router)
    dp.include_router(topup_router)
    dp.include_router(tasks_router)

    # Start background tasks
    asyncio.create_task(process_pending_rewards())

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
