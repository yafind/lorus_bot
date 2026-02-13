"""SubGram tasks handler with integrated utilities."""
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Union

import aiohttp
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import subgram_api
from database.models import User, PendingReward, UserSubscriptions
from handlers.tasks.referral_service import process_referral_reward
from loader import bot

logger = logging.getLogger(__name__)
router = Router()

SUBGRAM_REWARD = 2
SUBGRAM_URL = "https://api.subgram.org/request-op/"
TASK_CACHE_TTL = 12  # seconds
SUBGRAM_CACHE_TTL = 60  # seconds

# Cache for SubGram API responses
_SUBGRAM_CACHE = {}


# ============================================================================
# UTILITIES
# ============================================================================

async def fetch_subgram_links(
    user_id: str,
    chat_id: str,
    **kwargs
) -> Optional[Union[list[str], str]]:
    """
    Fetch SubGram task links for user.
    
    Returns:
        List of links, 'high_risk', or None
    """
    api_key = subgram_api.strip()
    if not api_key or api_key == "your_subgram_api_key":
        logger.warning("SubGram API key not configured")
        return None

    cache_key = (user_id, chat_id)
    now_ts = datetime.now().timestamp()

    # Clean old cache
    global _SUBGRAM_CACHE
    _SUBGRAM_CACHE = {
        k: v for k, v in _SUBGRAM_CACHE.items()
        if now_ts - v[1] < SUBGRAM_CACHE_TTL
    }

    # Check cache
    if cache_key in _SUBGRAM_CACHE:
        cached_links, cached_time = _SUBGRAM_CACHE[cache_key]
        if now_ts - cached_time < TASK_CACHE_TTL:
            return cached_links

    headers = {
        "Auth": api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    data = {"UserId": user_id, "ChatId": chat_id, **kwargs}

    timeout = aiohttp.ClientTimeout(total=15)
    for attempt in range(2):
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(SUBGRAM_URL, headers=headers, json=data) as resp:
                    if resp.status == 429:
                        logger.warning(f"SubGram rate limit for {user_id}")
                        await asyncio.sleep(3)
                        continue
                    if not resp.ok:
                        try:
                            json_resp = await resp.json()
                            message = json_resp.get("message", "")
                            if "высокий риск фейкового аккаунта" in message.lower():
                                logger.warning(
                                    f"⚠️ High-risk account detected for user {user_id} - "
                                    f"SubGram API warning: {message}"
                                )
                                return "high_risk"
                        except aiohttp.ContentTypeError:
                            pass
                        logger.error(f"SubGram HTTP {resp.status}")
                        return None
                    data_resp = await resp.json()
                    links = data_resp.get("links", [])
                    clean_links = [l.strip() for l in links if l and l.strip()]
                    _SUBGRAM_CACHE[cache_key] = (clean_links, now_ts)
                    return clean_links
        except asyncio.TimeoutError:
            logger.warning(f"SubGram timeout (attempt {attempt + 1}) for {user_id}")
            if attempt == 0:
                await asyncio.sleep(2)
            else:
                return None
        except Exception as e:
            logger.exception(f"SubGram fetch failed: {e}")
            return None

    return None




def create_navigation_keyboard(
    current_idx: int, 
    total: int, 
    go_link: str,
    prev_callback: str = "prev",
    next_callback: str = "next",
    check_callback: str = "check"
) -> dict:
    """Create navigation keyboard for task browsing."""
    builder = InlineKeyboardBuilder()
    
    # Navigation row
    row = []
    row.append(InlineKeyboardButton(
        text="⬅️" if current_idx == 0 else "⬅️ Назад", 
        callback_data=prev_callback
    ))
    row.append(InlineKeyboardButton(
        text=f"{current_idx + 1}/{total}", 
        callback_data="noop"
    ))
    row.append(InlineKeyboardButton(
        text="➡️" if current_idx == total - 1 else "Вперед ➡️", 
        callback_data=next_callback
    ))
    builder.row(*row)
    
    # Action buttons
    builder.row(InlineKeyboardButton(text="✅ Перейти к заданию", url=go_link))
    builder.row(InlineKeyboardButton(text="🔍 Проверить подписку", callback_data=check_callback))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="tasks"))
    
    return builder.as_markup()


async def log_subscription(user_id: int, channel_id: int) -> None:
    """Log user subscription."""
    UserSubscriptions.get_or_create(
        user_id=user_id,
        channel_id=channel_id,
        defaults={'timestamp': datetime.now()}
    )


def clear_subgram_cache() -> None:
    """Clear SubGram API cache (useful for testing)."""
    global _SUBGRAM_CACHE
    _SUBGRAM_CACHE = {}


# ============================================================================
# BUSINESS LOGIC
# ============================================================================

async def get_subgram_tasks(user_id: int, chat_id: int) -> list[dict]:
    """Get available SubGram tasks for user.
    
    Returns list of tasks not yet completed by user.
    Handles API errors gracefully and filters invalid links.
    """
    result = await fetch_subgram_links(
        user_id=str(user_id),
        chat_id=str(chat_id),
        first_name="",
        language_code="ru",
        premium=False,
    )

    # Handle API errors - return empty list
    if result is None:
        logger.debug(f"SubGram API returned None for user {user_id}")
        return []
    
    if result == "high_risk":
        logger.warning(f"User {user_id} detected as high-risk account by SubGram - showing other tasks")
        # Не блокируем пользователя, просто не показываем SubGram задания
        # Он все равно сможет видеть Flyer и Local задания
        return []

    # Ensure result is a list
    if not isinstance(result, list):
        logger.error(f"Unexpected SubGram API response type: {type(result)}")
        return []

    # Filter valid links - must start with proper Telegram URL schemes
    valid_links = [
        link.strip() for link in result
        if isinstance(link, str)
        and link.strip().startswith(("https://t.me/", "http://t.me/", "tg://"))
        and "api.subgram" not in link.lower()
        and "bot=" not in link.lower()
    ]

    if not valid_links:
        logger.debug(f"No valid SubGram links found for user {user_id}")
        return []

    # Get completed tasks
    completed = set(
        key for (key,) in PendingReward.select(
            PendingReward.task_key
        ).where(PendingReward.user_id == user_id).tuples()
        if key and str(key).startswith("subgram:")
    )

    # Build task list
    tasks = []
    for link in valid_links:
        if f"subgram:{link}" not in completed:
            # Extract channel name from link
            channel = link.split("/")[-1] if "/" in link else "канал"
            tasks.append({
                "type": "subgram",
                "link": link,
                "reward": SUBGRAM_REWARD,
                "channel": channel,
            })
    
    return tasks


async def show_subgram_task(call: CallbackQuery, state: FSMContext) -> None:
    """Display current SubGram task."""
    data = await state.get_data()
    subgram_tasks = data.get("subgram_tasks", [])
    idx = data.get("subgram_index", 0)

    if not subgram_tasks or idx >= len(subgram_tasks):
        return False

    task = subgram_tasks[idx]
    go_link = task.get("link", "")
    price = task.get("reward", SUBGRAM_REWARD)
    channel_name = task.get("channel", "канал")

    text = (
        "🚀 <b>Задание от SubGram!</b> 🚀\n\n"
        f"📢 <b>Действие:</b> Подпишитесь на @{channel_name}\n"
        f"💎 <b>Награда:</b> {price} 💎\n\n"
        "👉 Нажмите «✅ Перейти к заданию», затем подпишитесь."
    )

    kb = create_navigation_keyboard(
        idx, 
        len(subgram_tasks), 
        go_link=go_link,
        prev_callback="subgram_prev",
        next_callback="subgram_next",
        check_callback="subgram_check"
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


# ============================================================================
# HANDLERS
# ============================================================================

@router.callback_query(F.data == "subgram_prev")
async def prev_subgram(call: CallbackQuery, state: FSMContext) -> None:
    """Navigate to previous SubGram task."""
    data = await state.get_data()
    idx = data.get("subgram_index", 0)

    if idx > 0:
        await state.update_data(subgram_index=idx - 1)
        await show_subgram_task(call, state)
    else:
        await call.answer()


@router.callback_query(F.data == "subgram_next")
async def next_subgram(call: CallbackQuery, state: FSMContext) -> None:
    """Navigate to next SubGram task."""
    data = await state.get_data()
    subgram_tasks = data.get("subgram_tasks", [])
    idx = data.get("subgram_index", 0)

    if idx < len(subgram_tasks) - 1:
        await state.update_data(subgram_index=idx + 1)
        await show_subgram_task(call, state)
    else:
        await call.answer()


@router.callback_query(F.data == "subgram_check")
async def check_subgram_task(call: CallbackQuery, state: FSMContext) -> None:
    """Check SubGram task completion."""
    user_id = call.from_user.id
    data = await state.get_data()
    current_link = data.get("current_link")
    current_reward = int(data.get("current_reward", SUBGRAM_REWARD))

    if not current_link:
        await call.answer("❌ Нет активного задания.", show_alert=True)
        return

    # Fetch fresh data from SubGram API
    fresh_links = await fetch_subgram_links(
        user_id=str(user_id),
        chat_id=str(call.message.chat.id),
        first_name=call.from_user.first_name or "",
        language_code=call.from_user.language_code or "",
        premium=bool(call.from_user.is_premium),
    )

    if fresh_links is None:
        await call.answer("⚠️ Сервис временно недоступен. Попробуйте через 30 сек.", show_alert=True)
        return

    if fresh_links == "high_risk":
        await call.answer("⚠️ Ваш аккаунт заблокирован в SubGram.", show_alert=True)
        return

    # Check if link is completed
    if current_link in fresh_links:
        await call.answer("⏳ Похоже, вы ещё не подписались. Подождите и повторите.", show_alert=True)
        return

    # Task completed - save reward and update user

    scheduled_at = datetime.now() + timedelta(days=3)
    PendingReward.get_or_create(
        user_id=user_id,
        task_key=f"subgram:{current_link}",
        defaults={
            "task_title": f"задание «Подписка на канал {current_link}»",
            "diamonds": int(current_reward),
            "scheduled_at": scheduled_at,
            "status": "pending",
            "completed_at": datetime.now(),
        }
    )

    user = User.get_or_none(User.user_id == user_id)
    if user:
        user.task_count += 1
        user.task_count_diamonds += current_reward
        user.save()
        await process_referral_reward(user, current_reward)

    await call.answer(
        f"✅ Проверка пройдена! 💎 начислятся через 60 секунд.",
        show_alert=True
    )


@router.callback_query(F.data == "noop")
async def noop_handler(call: CallbackQuery) -> None:
    """No operation handler for pagination indicator."""
    await call.answer()
