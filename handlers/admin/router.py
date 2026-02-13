"""Admin module router."""
from aiogram import Router

# Import all sub-routers
from .stats import router as stats_router
from .balance import router as balance_router
from .tasks import router as tasks_router
from .gifts import router as gifts_router
from .admins import router as admins_router
from .broadcast import router as broadcast_router

# Create main router
router = Router()

# Include all sub-routers
router.include_router(stats_router)
router.include_router(balance_router)
router.include_router(tasks_router)
router.include_router(gifts_router)
router.include_router(admins_router)
router.include_router(broadcast_router)

__all__ = ["router"]
