from aiogram import Router

from . import add_task, tasks_view, subgram_tasks, flyer_tasks, local_tasks

router = Router()
router.include_router(add_task.router)
router.include_router(tasks_view.router)
router.include_router(subgram_tasks.router)
router.include_router(flyer_tasks.router)
router.include_router(local_tasks.router)