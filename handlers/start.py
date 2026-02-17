"""Bot start handler."""
import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from config import MINI_APP_URL
from database.models import User
from keyboards.keyboard import start_keyboard
from handlers.utils import create_user

logger = logging.getLogger(__name__)
router = Router()


@router.message(CommandStart())
async def start_handler(message: Message) -> None:
    """Handle /start command with referral tracking."""
    user = message.from_user
    user_id = user.id

    # Extract and validate referrer ID from deep link
    referrer_id = None
    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        candidate = args[1].strip()
        if candidate.isdigit() and int(candidate) != user_id:
            candidate_id = int(candidate)
            # Critical: Only accept existing users as referrers
            if User.select().where(User.user_id == candidate_id).exists():
                referrer_id = candidate_id
                logger.debug(f"Valid referral: {user_id} ← {referrer_id}")
            else:
                logger.debug(f"Invalid referrer ID {candidate_id} for user {user_id}")

    # Create or update user
    existing_user = User.get_or_none(User.user_id == user_id)
    if not existing_user:
        create_user(user_id, referrer_id, user)
        welcome_type = "new"
    else:
        # Prevent referral hijacking on subsequent starts
        if referrer_id and not existing_user.referral:
            existing_user.referral = referrer_id
            existing_user.save()
            logger.info(f"Late referral attached for user {user_id}: {referrer_id}")
        
        existing_user.last_active = datetime.now()
        existing_user.save()
        welcome_type = "returning"

    # Personalized welcome message
    if welcome_type == "new":
        if referrer_id:
            text = (
                "✨ Добро пожаловать в бота!\n\n"
                "💎 Вы перешли по реферальной ссылке\n"
                "🎮 Выполняйте задания и играйте в мини-игры,\n"
                "чтобы собирать алмазы и обменивать их на подарки!"
            )
        else:
            text = (
                "✨ Добро пожаловать в бота!\n\n"
                "🎮 Выполняйте задания и играйте в мини-игры,\n"
                "чтобы собирать алмазы и обменивать их на подарки!"
            )
    else:
        text = (
            "✨ С возвращением!\n\n"
            "🎮 Продолжайте выполнять задания и играть,\n"
            "чтобы копить алмазы для обмена на подарки!"
        )

    try:
        await message.answer(
            text,
            reply_markup=start_keyboard(user_id, MINI_APP_URL),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.exception(f"Failed to send welcome message to {user_id}: {e}")
        # Fallback without parse_mode
        clean_text = text.replace("<b>", "").replace("</b>", "")
        await message.answer(clean_text, reply_markup=start_keyboard(user_id, MINI_APP_URL))


@router.callback_query(F.data == "hide_referral")
async def hide_referral(call: CallbackQuery) -> None:
    """Safely hide referral message."""
    try:
        await call.message.delete()
    except Exception as e:
        logger.debug(f"Failed to delete referral message: {e}")
        try:
            await call.message.edit_text("Сообщение скрыто ✅")
        except:
            pass
    await call.answer()
