"""Flyer tasks handler."""
import asyncio
import logging
import inspect
from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest
from flyerapi import Flyer # type: ignore

from config import FLYER_KEY
from database.models import User, PendingReward
from handlers.tasks.referral_service import process_referral_reward
from handlers.tasks.subgram_tasks import create_navigation_keyboard

logger = logging.getLogger(__name__)
router = Router()

flyer = Flyer(FLYER_KEY)


async def _flyer_get_tasks(user_id: int) -> list[dict]:
    """Fetch tasks from Flyer API with method fallback for different SDK versions."""
    candidates = [
        ("get_tasks", {"user_id": user_id, "language_code": "ru", "limit": 5}),
        ("tasks", {"user_id": user_id, "language_code": "ru", "limit": 5}),
        ("get_tasks_list", {"user_id": user_id, "language_code": "ru", "limit": 5}),
        ("get_offers", {"user_id": user_id, "language_code": "ru", "limit": 5}),
    ]

    for name, kwargs in candidates:
        fn = getattr(flyer, name, None)
        if not fn:
            continue
        try:
            result = fn(**kwargs)
            if inspect.isawaitable(result):
                result = await result
            return result if isinstance(result, list) else []
        except TypeError:
            # Try calling with only user_id if signature differs
            try:
                result = fn(user_id=user_id)
                if inspect.isawaitable(result):
                    result = await result
                return result if isinstance(result, list) else []
            except Exception as e:
                logger.exception(f"Flyer API method {name} failed: {e}")
        except Exception as e:
            logger.exception(f"Flyer API method {name} failed: {e}")

    # Fallback to generic request-style methods if present
    for request_name in ("request", "api_request", "call", "_request"):
        fn = getattr(flyer, request_name, None)
        if not fn:
            continue
        for action in ("get_tasks", "tasks", "get_tasks_list", "get_offers"):
            try:
                result = fn(action, user_id=user_id, language_code="ru", limit=5)
                if inspect.isawaitable(result):
                    result = await result
                return result if isinstance(result, list) else []
            except TypeError:
                try:
                    result = fn(action, {"user_id": user_id, "language_code": "ru", "limit": 5})
                    if inspect.isawaitable(result):
                        result = await result
                    return result if isinstance(result, list) else []
                except Exception as e:
                    logger.exception(f"Flyer API {request_name}({action}) failed: {e}")
            except Exception as e:
                logger.exception(f"Flyer API {request_name}({action}) failed: {e}")

    logger.error("Flyer API: no compatible task method found")
    return []


async def get_flyer_tasks(user_id: int) -> list[dict]:
    """Get available Flyer tasks for user.
    
    Returns list of active tasks not yet completed by user.
    Filters by status (incomplete/abort) and minimum price >= 1.
    """
    try:
        tasks_raw = await _flyer_get_tasks(user_id)
    except Exception as e:
        logger.exception(f"Flyer API error getting tasks for user {user_id}: {e}")
        return []

    if not tasks_raw:
        logger.debug(f"No tasks from Flyer API for user {user_id}")
        return []

    # Filter active tasks - only incomplete/abort with price >= 1
    active_tasks = [
        t for t in tasks_raw
        if isinstance(t, dict)
        and t.get("status") in ("incomplete", "abort")
        and t.get("price", 0) >= 1
    ]

    if not active_tasks:
        logger.debug(f"No active Flyer tasks for user {user_id}")
        return []

    # Get completed tasks
    completed = set(
        key for (key,) in PendingReward.select(
            PendingReward.task_key
        ).where(PendingReward.user_id == user_id).tuples()
        if key and str(key).startswith("flyer:")
    )

    # Build task list
    tasks = []
    for task in active_tasks:
        # Validate resource_id exists
        resource_id = task.get("resource_id")
        if resource_id is None:
            logger.warning(f"Flyer task missing resource_id: {task}")
            continue

        flyer_id = f"flyer:{resource_id}"
        
        if f"flyer:{resource_id}" not in completed:
            # Safely extract link
            link = (
                task.get("link")
                or (task.get("links") and task["links"][0] if isinstance(task.get("links"), list) else None)
                or ""
            )
            
            if not link:
                logger.warning(f"Flyer task has no valid link: {task}")
                continue

            tasks.append({
                "type": "flyer",
                "link": link,
                "reward": task.get("price", 0),
                "channel": task.get("name", "Канал"),
                "task_data": task,
            })
    
    return tasks


async def show_flyer_task(call: CallbackQuery, state: FSMContext) -> None:
    """Display current Flyer task."""
    data = await state.get_data()
    flyer_tasks = data.get("flyer_tasks", [])
    idx = data.get("flyer_index", 0)

    if not flyer_tasks or idx >= len(flyer_tasks):
        return False

    task = flyer_tasks[idx]
    go_link = task.get("link", "")
    price = task.get("reward", 0)
    name = task.get("channel", "Канал")

    text = (
        "🚀 <b>Задание от Flyer!</b> 🚀\n\n"
        f"📢 <b>Подпишитесь на:</b> {name}\n"
        f"💎 <b>Награда:</b> {price} 💎\n\n"
        "👉 Нажмите «✅ Перейти к заданию», затем подпишитесь."
    )

    kb = create_navigation_keyboard(
        idx, 
        len(flyer_tasks), 
        go_link=go_link,
        prev_callback="flyer_prev",
        next_callback="flyer_next",
        check_callback="flyer_check"
    )

    try:
        await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        logger.exception(f"Failed to edit message: {e}")

    await state.update_data(
        current_task=task,
        current_link=go_link,
        current_reward=price
    )
    
    return True


@router.callback_query(F.data == "flyer_prev")
async def prev_flyer(call: CallbackQuery, state: FSMContext) -> None:
    """Navigate to previous Flyer task."""
    data = await state.get_data()
    idx = data.get("flyer_index", 0)

    if idx > 0:
        await state.update_data(flyer_index=idx - 1)
        await show_flyer_task(call, state)
    else:
        await call.answer()


@router.callback_query(F.data == "flyer_next")
async def next_flyer(call: CallbackQuery, state: FSMContext) -> None:
    """Navigate to next Flyer task."""
    data = await state.get_data()
    flyer_tasks = data.get("flyer_tasks", [])
    idx = data.get("flyer_index", 0)

    if idx < len(flyer_tasks) - 1:
        await state.update_data(flyer_index=idx + 1)
        await show_flyer_task(call, state)
    else:
        await call.answer()


@router.callback_query(F.data == "flyer_check")
async def check_flyer_task(call: CallbackQuery, state: FSMContext) -> None:
    """Check Flyer task completion."""
    user_id = call.from_user.id
    data = await state.get_data()
    current_task = data.get("current_task")

    if not current_task:
        await call.answer("❌ Нет активного задания.", show_alert=True)
        return

    signature = current_task.get("task_data", {}).get("signature")
    resource_id = current_task.get("task_data", {}).get("resource_id")
    price = current_task.get("reward", 0)

    if not signature or resource_id is None:
        await call.answer("❌ Некорректное задание.", show_alert=True)
        return

    loop = asyncio.get_event_loop()
    
    # Check if reward already received
    existing = await loop.run_in_executor(
        None,
        lambda: PendingReward.get_or_none(
            PendingReward.user_id == user_id,
            PendingReward.task_key == f"flyer:{resource_id}"
        )
    )
    if existing and existing.created_at > datetime.now() - timedelta(hours=48):
        await call.answer("✅ Награда за это задание уже получена.", show_alert=True)
        return

    try:
        result = await flyer.check_task(user_id=user_id, signature=signature)
        status = result if isinstance(result, str) else None
    except Exception as e:
        logger.exception(f"Flyer check_task failed for {user_id}: {e}")
        await call.answer("⚠️ Ошибка при проверке. Попробуйте позже.", show_alert=True)
        return

    if status == "complete":
        user = await loop.run_in_executor(
            None,
            lambda: User.get_or_none(User.user_id == user_id)
        )
        if not user:
            await call.answer("⚠️ Пользователь не найден.", show_alert=True)
            return

        # Create pending reward
        scheduled_at = datetime.now() + timedelta(days=3)
        PendingReward.get_or_create(
            user_id=user_id,
            task_key=f"flyer:{resource_id}",
            defaults={
                "task_title": f"задание «Подписка на канал {resource_id}»",
                "diamonds": int(price),
                "scheduled_at": scheduled_at,
                "status": "pending",
                "completed_at": datetime.now(),
            }
        )

        user.balance += price
        user.task_count += 1
        await loop.run_in_executor(None, lambda: user.save())

        await process_referral_reward(user, float(price))

        await call.answer(f"✅ Успех! Получено {price} 💎.", show_alert=True)

    elif status in ("waiting", "checking"):
        await call.answer("⏳ Подписка обнаружена! Окончательная проверка через 24 часа.", show_alert=True)

    else:
        await call.answer("❌ Подписка не обнаружена. Убедитесь, что вы подписались.", show_alert=True)
