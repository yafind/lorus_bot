"""Unified tasks view handler - SubGram → Flyer → Local."""
import logging
from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database.models import User, UserSubscriptions, PendingReward, Task
from handlers.tasks.subgram_tasks import get_subgram_tasks, fetch_subgram_links
from handlers.tasks.flyer_tasks import get_flyer_tasks, flyer
from handlers.tasks.local_tasks import get_local_tasks, is_subscribed, _is_fraud_attempt

logger = logging.getLogger(__name__)
router = Router()

TASK_REWARD_DELAY_DAYS = 3


class TasksView(StatesGroup):
    """FSM states for viewing tasks."""
    viewing = State()


def _back_keyboard() -> dict:
    """Create back button keyboard."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="back"))
    return builder.as_markup()


def _task_key(task: dict) -> str:
    source = task.get("source")
    if source == "subgram":
        return f"subgram:{task.get('link', '')}"
    if source == "flyer":
        resource_id = task.get("task_data", {}).get("resource_id")
        return f"flyer:{resource_id}"
    if source == "local":
        return f"local:{task.get('task_id')}"
    return "unknown"


def _task_title(task: dict) -> str:
    channel = task.get("channel", "канал")
    return f"задание «Подписка на канал {channel}»"


def _build_task_text(task: dict, idx: int, total: int) -> str:
    reward = int(task.get("reward", 0))
    remaining = total - idx
    
    return (
        f"<b>📌 Задание {idx + 1} из {total}</b>\n"
        f"Осталось: <b>{remaining}</b> заданий\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"💎 <b>Награда:</b> <code>{reward}</code> алмазов\n"
        f"⏳ <b>Статус:</b> Ожидает выполнения\n"
        f"━━━━━━━━━━━━━━━━\n\n"
        f"<b>Инструкция:</b>\n"
        f"1️⃣ Нажмите <b>«Перейти»</b> и подпишитесь\n"
        f"2️⃣ Вернитесь в бот и нажмите <b>«Проверить»</b>\n"
        f"3️⃣ Награда будет начислена через 3 дня"
    )


def _build_task_keyboard(task: dict, show_refresh: bool = False) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    if show_refresh:
        builder.row(InlineKeyboardButton(text="🔄 Обновить", callback_data="tasks_refresh"))
        return builder

    link = task.get("link", "")
    if link:
        builder.row(InlineKeyboardButton(text="🔗 Перейти в канал", url=link))
    
    # Верхний ряд с кнопкой проверки
    builder.row(InlineKeyboardButton(text="✅ Проверить задание", callback_data="task_check"))
    
    # Нижний ряд: Пропустить и Назад
    builder.row(
        InlineKeyboardButton(text="⏭️ Пропустить", callback_data="task_next"),
        InlineKeyboardButton(text="⬅️ Назад", callback_data="back")
    )
    return builder


async def _show_no_tasks_message(call: CallbackQuery, state: FSMContext) -> None:
    """Show message when no tasks available."""
    text = (
        "<b>📭 Заданий пока нет</b>\n\n"
        "😴 Новые задания появляются регулярно.\n"
        "⏰ Попробуйте позже!\n\n"
        "💡 <i>Совет: Проверяйте задания несколько раз в день</i>"
    )
    kb = _back_keyboard()
    try:
        await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        try:
            await call.message.delete()
        except Exception:
            pass
        await call.message.answer(text, reply_markup=kb, parse_mode="HTML")
    await state.clear()


async def _show_all_completed_message(call: CallbackQuery, state: FSMContext) -> None:
    """Show message when all tasks completed."""
    text = (
        "<b>✅ Все доступные задания завершены!</b>\n\n"
        "🎉 Отличная работа!\n\n"
        "📊 <b>Что дальше:</b>\n"
        "💎 Награды будут начислены через 3 дня\n"
        "🔄 Новые задания появляются регулярно\n"
        "🎯 Продолжайте выполнять задания каждый день!\n\n"
        "<i>Совет: Максимизируйте доход, выполняя все типы заданий</i>"
    )
    kb = _build_task_keyboard({}, show_refresh=True)
    try:
        await call.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    except Exception:
        try:
            await call.message.delete()
        except Exception:
            pass
        await call.message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await state.clear()


@router.callback_query(F.data == "tasks")
async def show_tasks_callback(call: CallbackQuery, state: FSMContext) -> None:
    """Handle tasks button callback."""
    await show_tasks(call, state)


async def show_tasks_from_message(message: Message, state: FSMContext) -> None:
    """Entry point for tasks from message button."""
    user_id = message.from_user.id
    chat_id = message.chat.id

    all_tasks = await _load_tasks(user_id, chat_id)
    if not all_tasks:
        await message.answer("Заданий нет", parse_mode="HTML")
        return

    await state.update_data(all_tasks=all_tasks, current_task_index=0, skipped_keys=[])
    await _send_current_task_message(message, state)


async def show_tasks(call: CallbackQuery, state: FSMContext) -> None:
    """Show tasks in priority order: SubGram → Flyer → Local."""
    user_id = call.from_user.id
    chat_id = call.message.chat.id

    try:
        all_tasks = await _load_tasks(user_id, chat_id)
        if not all_tasks:
            await _show_no_tasks_message(call, state)
            return

        await state.update_data(all_tasks=all_tasks, current_task_index=0, skipped_keys=[])
        await _show_current_task(call, state)
    except Exception as e:
        logger.exception(f"Error loading tasks for user {user_id}: {e}")
        text = "⚠️ Ошибка при загрузке заданий. Попробуйте позже."
        kb = _back_keyboard()
        try:
            await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass
        await state.clear()


async def _load_tasks(user_id: int, chat_id: int) -> list[dict]:
    logger.info(f"Loading tasks for user {user_id}...")
    
    subgram_tasks = await get_subgram_tasks(user_id, chat_id)
    logger.info(f"[SubGram] Loaded {len(subgram_tasks)} tasks for user {user_id}")
    
    flyer_tasks = await get_flyer_tasks(user_id)
    logger.info(f"[Flyer] Loaded {len(flyer_tasks)} tasks for user {user_id}")
    
    local_tasks = await get_local_tasks(user_id)
    logger.info(f"[Local] Loaded {len(local_tasks)} tasks for user {user_id}")

    total_tasks = len(subgram_tasks) + len(flyer_tasks) + len(local_tasks)
    logger.info(f"Total tasks loaded for user {user_id}: {total_tasks} (SubGram: {len(subgram_tasks)}, Flyer: {len(flyer_tasks)}, Local: {len(local_tasks)})")

    return [
        *[{**t, "source": "subgram"} for t in subgram_tasks],
        *[{**t, "source": "flyer"} for t in flyer_tasks],
        *[{**t, "source": "local"} for t in local_tasks],
    ]


async def _show_current_task(call: CallbackQuery, state: FSMContext) -> None:
    """Display current task with unified UI."""
    data = await state.get_data()
    all_tasks = data.get("all_tasks", [])
    current_idx = data.get("current_task_index", 0)

    if not all_tasks or current_idx >= len(all_tasks):
        await _show_all_completed_message(call, state)
        return

    task = all_tasks[current_idx]
    text = _build_task_text(task, current_idx, len(all_tasks))
    kb = _build_task_keyboard(task)
    await call.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")


async def _send_current_task_message(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    all_tasks = data.get("all_tasks", [])
    current_idx = data.get("current_task_index", 0)

    if not all_tasks or current_idx >= len(all_tasks):
        await message.answer("Заданий нет", parse_mode="HTML")
        return

    task = all_tasks[current_idx]
    text = _build_task_text(task, current_idx, len(all_tasks))
    kb = _build_task_keyboard(task)
    await message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")


@router.callback_query(F.data == "task_next")
async def next_task(call: CallbackQuery, state: FSMContext) -> None:
    """Skip current task and move to next."""
    data = await state.get_data()
    all_tasks = data.get("all_tasks", [])
    current_idx = data.get("current_task_index", 0)

    if not all_tasks or current_idx >= len(all_tasks):
        await _show_all_completed_message(call, state)
        return

    skipped = set(data.get("skipped_keys", []))
    skipped.add(_task_key(all_tasks[current_idx]))

    if current_idx < len(all_tasks) - 1:
        await state.update_data(current_task_index=current_idx + 1, skipped_keys=list(skipped))
        await _show_current_task(call, state)
    else:
        await _show_all_completed_message(call, state)


@router.callback_query(F.data == "task_check")
async def check_task(call: CallbackQuery, state: FSMContext) -> None:
    """Check task completion for current task."""
    data = await state.get_data()
    all_tasks = data.get("all_tasks", [])
    current_idx = data.get("current_task_index", 0)

    if not all_tasks or current_idx >= len(all_tasks):
        await call.answer("❌ Нет активного задания.", show_alert=True)
        return

    task = all_tasks[current_idx]
    source = task.get("source")

    if source == "subgram":
        ok = await _check_subgram(call, task)
    elif source == "flyer":
        ok = await _check_flyer(call, task)
    elif source == "local":
        ok = await _check_local(call, task)
    else:
        ok = False

    if ok:
        await _advance_after_completion(call, state)


@router.callback_query(F.data == "back")
async def back_button(call: CallbackQuery, state: FSMContext) -> None:
    """Handle back button."""
    await state.clear()
    await call.answer()


@router.callback_query(F.data == "tasks_refresh")
async def refresh_tasks(call: CallbackQuery, state: FSMContext) -> None:
    """Reload tasks queue."""
    await show_tasks(call, state)


async def _advance_after_completion(call: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    all_tasks = data.get("all_tasks", [])
    current_idx = data.get("current_task_index", 0)

    if current_idx < len(all_tasks) - 1:
        await state.update_data(current_task_index=current_idx + 1)
        await _show_current_task(call, state)
    else:
        await _show_all_completed_message(call, state)


async def _schedule_reward(user_id: int, task: dict) -> None:
    task_key = _task_key(task)
    diamonds = int(task.get("reward", 0))
    if not task_key or diamonds <= 0:
        return

    scheduled_at = datetime.now() + timedelta(days=TASK_REWARD_DELAY_DAYS)
    PendingReward.get_or_create(
        user_id=user_id,
        task_key=task_key,
        defaults={
            "task_title": _task_title(task),
            "diamonds": diamonds,
            "scheduled_at": scheduled_at,
            "status": "pending",
            "completed_at": datetime.now(),
        }
    )


async def _check_subgram(call: CallbackQuery, task: dict) -> bool:
    user_id = call.from_user.id
    link = task.get("link", "")
    if not link:
        await call.answer("❌ Ссылка недоступна.", show_alert=True)
        return False

    logger.info(f"[SubGram] User {user_id} checking task: {link}")

    fresh_links = await fetch_subgram_links(
        user_id=str(user_id),
        chat_id=str(call.message.chat.id),
        first_name=call.from_user.first_name or "",
        language_code=call.from_user.language_code or "ru",
        premium=bool(call.from_user.is_premium),
    )

    if fresh_links is None:
        logger.warning(f"[SubGram] Service unavailable for user {user_id}")
        await call.answer("⚠️ Сервис временно недоступен. Попробуйте позже.", show_alert=True)
        return False

    if fresh_links == "high_risk":
        logger.warning(f"[SubGram] High-risk account blocked: user {user_id}")
        await call.answer("⚠️ Ваш аккаунт заблокирован в SubGram.", show_alert=True)
        return False

    if link in fresh_links:
        logger.info(f"[SubGram] Task NOT completed by user {user_id}: still in fresh links")
        await call.answer("❌ Не выполнено. Попробуйте ещё раз.", show_alert=True)
        return False

    await _schedule_reward(user_id, task)
    logger.info(f"[SubGram] ✅ Task COMPLETED by user {user_id}: {link}, reward: {task.get('reward')}")
    await call.answer("✅ Выполнено. Награда будет начислена через 3 дня.", show_alert=True)
    return True


async def _check_flyer(call: CallbackQuery, task: dict) -> bool:
    user_id = call.from_user.id
    data = task.get("task_data", {})
    signature = data.get("signature")
    resource_id = data.get("resource_id")

    if not signature or resource_id is None:
        await call.answer("❌ Некорректное задание.", show_alert=True)
        return False

    logger.info(f"[Flyer] User {user_id} checking task: resource_id={resource_id}")

    try:
        result = await flyer.check_task(user_id=user_id, signature=signature)
        status = result if isinstance(result, str) else None
    except Exception as e:
        logger.exception(f"[Flyer] check_task failed for user {user_id}: {e}")
        await call.answer("⚠️ Ошибка при проверке. Попробуйте позже.", show_alert=True)
        return False

    if status == "complete":
        await _schedule_reward(user_id, task)
        logger.info(f"[Flyer] ✅ Task COMPLETED by user {user_id}: resource_id={resource_id}, reward: {task.get('reward')}")
        await call.answer("✅ Выполнено. Награда будет начислена через 3 дня.", show_alert=True)
        return True

    if status in ("waiting", "checking"):
        logger.info(f"[Flyer] Task status '{status}' for user {user_id}: resource_id={resource_id}")
        await call.answer("⏳ Подписка обнаружена. Проверка через 24 часа.", show_alert=True)
        return False

    logger.info(f"[Flyer] Task NOT completed by user {user_id}: status={status}, resource_id={resource_id}")
    await call.answer("❌ Не выполнено. Попробуйте ещё раз.", show_alert=True)
    return False


async def _check_local(call: CallbackQuery, task: dict) -> bool:
    user_id = call.from_user.id
    task_id = task.get("task_id")
    chat_id = task.get("chat_id")

    if not task_id or not chat_id:
        await call.answer("❌ Некорректное задание.", show_alert=True)
        return False

    logger.info(f"[Local] User {user_id} checking task: task_id={task_id}, chat_id={chat_id}")

    channel_id_val = int(chat_id)
    if UserSubscriptions.select().where(
        (UserSubscriptions.user_id == user_id) &
        (UserSubscriptions.channel_id == channel_id_val)
    ).exists():
        logger.info(f"[Local] Task already claimed by user {user_id}: task_id={task_id}")
        await call.answer("✅ Уже получено!", show_alert=True)
        return False

    if not await is_subscribed(user_id, chat_id):
        logger.info(f"[Local] User {user_id} NOT subscribed to chat_id={chat_id}")
        await call.answer("❌ Не выполнено. Попробуйте ещё раз.", show_alert=True)
        return False

    if await _is_fraud_attempt(user_id, channel_id_val):
        logger.warning(f"[Local] ⚠️ FRAUD DETECTED for user {user_id} on chat_id={chat_id}")
        user = User.get_or_none(User.user_id == user_id)
        if user:
            user.balance = max(0, user.balance - 10)
            user.task_count = max(0, user.task_count - 5)
            user.task_count_diamonds = max(0, user.task_count_diamonds - 5)
            user.save()
            UserSubscriptions.delete().where(UserSubscriptions.user_id == user_id).execute()
        await call.answer("⚠️ Накрутка! Награда отменена.", show_alert=True)
        return False

    UserSubscriptions.get_or_create(
        user_id=user_id,
        channel_id=channel_id_val,
        defaults={"timestamp": datetime.now()}
    )

    Task.update(
        current_subscribers=Task.current_subscribers + 1
    ).where(Task.id == task_id).execute()

    await _schedule_reward(user_id, task)
    logger.info(f"[Local] ✅ Task COMPLETED by user {user_id}: task_id={task_id}, chat_id={chat_id}, reward: {task.get('reward')}")
    await call.answer("✅ Выполнено. Награда будет начислена через 3 дня.", show_alert=True)
    return True
