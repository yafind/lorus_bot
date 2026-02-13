"""Local tasks handler."""
import logging
from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from database.models import Task, User, UserSubscriptions, PendingReward
from handlers.tasks.referral_service import process_referral_reward
from handlers.tasks.subgram_tasks import log_subscription
from loader import bot
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

logger = logging.getLogger(__name__)
router = Router()


async def is_subscribed(user_id: int, chat_id: int) -> bool:
    """Check if user is subscribed to chat."""
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in ("member", "administrator", "creator", "restricted")
    except Exception as e:
        logger.debug(f"Failed to check subscription for {user_id} in {chat_id}: {e}")
        return False


def get_local_task_keyboard(invite_link: str) -> dict:
    """Create keyboard for local task."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✅ Перейти в канал", url=invite_link))
    builder.row(InlineKeyboardButton(text="🔍 Проверить подписку", callback_data="local_check_task"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="tasks"))
    return builder.as_markup()


async def get_local_tasks(user_id: int) -> list[dict]:
    """Get available local tasks for user.
    
    Returns list of active tasks not yet completed by user.
    """
    # Get completed task IDs
    completed_ids = set(
        cid for (cid,) in UserSubscriptions.select(
            UserSubscriptions.channel_id
        ).where(UserSubscriptions.user_id == user_id).tuples()
        if cid is not None
    )

    # Get active tasks not completed by user
    query = Task.select().where(Task.is_active)
    if completed_ids:
        query = query.where(~Task.chat_id.in_(completed_ids))

    # Build task list
    tasks = []
    for task in query:
        # Try to get channel title, fallback to default if fails
        channel_title = "Канал"
        try:
            chat = await bot.get_chat(chat_id=task.chat_id)
            if chat.title:
                channel_title = chat.title
        except Exception as e:
            logger.warning(f"Failed to get chat info for {task.chat_id}: {e}")

        tasks.append({
            "type": "local",
            "link": task.invite_link,
            "reward": task.reward,
            "channel": channel_title,
            "task_id": task.id,
            "chat_id": task.chat_id,
        })
    
    return tasks


async def show_local_task(call: CallbackQuery, state: FSMContext) -> None:
    """Display current local task."""
    data = await state.get_data()
    local_tasks = data.get("local_tasks", [])
    idx = data.get("local_index", 0)

    if not local_tasks or idx >= len(local_tasks):
        return False

    task = local_tasks[idx]
    invite_link = task.get("link", "")
    reward = task.get("reward", 0)
    channel_title = task.get("channel", "Канал")

    text = f"💎 <b>Подпишитесь на канал</b> 💎\n\n<b>{channel_title}</b>\n\nНаграда: {reward} 💎"
    
    kb = get_local_task_keyboard(invite_link)

    try:
        await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        logger.exception(f"Failed to edit message: {e}")

    await state.update_data(current_task_id=task.get("task_id"))
    
    return True


@router.callback_query(F.data == "local_check_task")
async def check_local_task(call: CallbackQuery, state: FSMContext) -> None:
    """Check local task completion."""
    data = await state.get_data()
    task_id = data.get("current_task_id")

    if not task_id:
        await call.answer("Нет активного задания.", show_alert=True)
        return

    task = Task.get_or_none(Task.id == task_id, Task.is_active == True)
    if not task:
        await call.answer("Задание недоступно.", show_alert=True)
        return

    user_id = call.from_user.id
    channel_id_val = int(task.chat_id)

    # Check if already completed
    if UserSubscriptions.select().where(
        (UserSubscriptions.user_id == user_id) &
        (UserSubscriptions.channel_id == channel_id_val)
    ).exists():
        await call.answer("✅ Уже получено!", show_alert=True)
        return

    # Check if subscribed
    if not await is_subscribed(user_id, task.chat_id):
        await call.answer("❌ Вы не подписаны на канал!", show_alert=True)
        return

    # Fraud detection
    if await _is_fraud_attempt(user_id, channel_id_val):
        user = User.get_or_none(User.user_id == user_id)
        if user:
            user.balance = max(0, user.balance - 10)
            user.task_count = max(0, user.task_count - 5)
            user.task_count_diamonds = max(0, user.task_count_diamonds - 5)
            user.save()
            UserSubscriptions.delete().where(UserSubscriptions.user_id == user_id).execute()
        await call.answer("⚠️ Накрутка! Награда отменена.", show_alert=True)
        await state.clear()
        return

    # Save pending reward
    scheduled_at = datetime.now() + timedelta(days=3)
    PendingReward.get_or_create(
        user_id=user_id,
        task_key=f"local:{task_id}",
        defaults={
            "task_title": f"задание «Подписка на канал {channel_id_val}»",
            "diamonds": int(task.reward),
            "scheduled_at": scheduled_at,
            "status": "pending",
            "completed_at": datetime.now(),
        }
    )

    # Log subscription
    await log_subscription(user_id, channel_id_val)

    # Update task stats
    Task.update(
        current_subscribers=Task.current_subscribers + 1
    ).where(Task.id == task_id).execute()

    # Update user stats
    user = User.get_or_none(User.user_id == user_id)
    if user:
        user.task_count += 1
        user.task_count_diamonds += task.reward
        user.save()
        await process_referral_reward(user, task.reward)

    await call.answer(
        f"✅ Проверка пройдена! Получите {task.reward} 💎 через 3 дня.",
        show_alert=True
    )


async def _is_fraud_attempt(user_id: int, channel_id: int) -> bool:
    """Check if multiple verification attempts in short time (fraud detection)."""
    hour_ago = datetime.now() - timedelta(hours=1)
    return UserSubscriptions.select().where(
        (UserSubscriptions.user_id == user_id) &
        (UserSubscriptions.channel_id == channel_id) &
        (UserSubscriptions.timestamp > hour_ago)
    ).count() >= 2
