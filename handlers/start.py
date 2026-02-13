"""Bot start and main menu handlers."""
import logging
import re
from datetime import datetime
from html import escape
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from database.models import User, Gift
from keyboards.keyboard import start_keyboard, toggle_ref_reward_keyboard, minigame_keyboard, dynamic_gifts_keyboard
from handlers.admin.core import is_admin

logger = logging.getLogger(__name__)
router = Router()


def _create_user(user_id: int, referrer_id: int | None, tg_user) -> User:
    """Create new user with referral tracking and safety checks."""
    # Sanitize username for DB constraints and safety
    raw_username = tg_user.username or tg_user.first_name or f"user{user_id}"
    # Allow only safe characters; replace others with underscore
    username = re.sub(r'[^\w\-_.]', '_', raw_username[:32]).strip('_') or f"user{user_id}"

    # Create user record
    user = User.create(
        user_id=user_id,
        username=username,
        balance=0,
        date=datetime.now(),
        referral=referrer_id,
        boost=False,
        last_farm_time=None,
        last_active=datetime.now(),
        task_count=0,
        task_count_diamonds=0,
        can_exchange=False,
        referrals_count=0,
        is_active_referral=False
    )
    
    # Update referrer's count if valid referral
    if referrer_id:
        try:
            referrer = User.get_by_id(referrer_id)
            referrer.referrals_count += 1
            referrer.save()
            logger.info(f"Referral tracked: user {user_id} → referrer {referrer_id}")
        except User.DoesNotExist:
            logger.warning(f"Invalid referrer ID {referrer_id} for new user {user_id}")
    
    return user


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
        _create_user(user_id, referrer_id, user)
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
            reply_markup=start_keyboard(user_id),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.exception(f"Failed to send welcome message to {user_id}: {e}")
        # Fallback without parse_mode
        clean_text = text.replace("<b>", "").replace("</b>", "")
        await message.answer(clean_text, reply_markup=start_keyboard(user_id))


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


# ===== MAIN MENU HANDLERS =====

@router.message(F.text == "✅ Задания")
async def tasks_button(message: Message, state: FSMContext) -> None:
    """Handle tasks button with proper state management."""
    try:
        from handlers.tasks.tasks_view import show_tasks_from_message
        await show_tasks_from_message(message, state)
    except Exception as e:
        logger.exception(f"Error loading tasks for user {message.from_user.id}: {e}")
        await message.answer("⚠️ Ошибка при загрузке заданий. Попробуйте позже.")


@router.message(F.text == "🍄 Профиль")
async def profile_button(message: Message) -> None:
    """Show detailed user profile with stats."""
    try:
        from handlers.profile import build_profile_text_simple
        user = User.get(User.user_id == message.from_user.id)

        active_refs = User.select().where(
            (User.referral == user.user_id) &
            (User.is_active_referral == True)
        ).count()
        inactive_refs = User.select().where(
            (User.referral == user.user_id) &
            (User.is_active_referral == False)
        ).count()

        # Экранируем full_name, чтобы не сломать HTML
        safe_full_name = escape(message.from_user.full_name)

        profile_text = build_profile_text_simple(
            user.user_id,
            safe_full_name,
            user,
            active_refs,
            inactive_refs
        )
        profile_text += "\n\n⬇️ Награда от рефералов ⬇️"

        await message.answer(
            profile_text,
            parse_mode="HTML",
            reply_markup=toggle_ref_reward_keyboard(is_showing=False)
        )
    except User.DoesNotExist:
        await message.answer("Сначала начните работу с ботом через /start")


@router.message(F.text == "📝 Добавить задание")
async def add_task_button(message: Message, state: FSMContext) -> None:
    """Start task creation flow with proper FSM context."""
    await state.clear()  # ← Важно: сбросить текущее состояние
    from handlers.tasks.add_task import add_task_start
    await add_task_start(message, state)


@router.message(F.text == "🎰 Мини-игры")
async def minigame_button(message: Message) -> None:
    """Show minigames menu."""
    user = User.get_or_none(User.user_id == message.from_user.id)
    balance = f"{int(user.balance)}" if user else "0"
    await message.answer(
        "🎮 <b>Мини-игры</b>\n\n"
        f"💰 Баланс: {balance} 💎\n"
        "💎 Стоимость игры: <b>5</b>\n\n"
        "• 🎲 Кубик\n"
        "• 🏀 Баскетбол\n"
        "• ⚽ Футбол\n"
        "• 🎯 Дартс\n"
        "• 🎳 Боулинг\n"
        "• 🎰 Слоты\n\n"
        "Выберите игру в меню ниже",
        parse_mode="HTML",
        reply_markup=minigame_keyboard()
    )


@router.message(F.text == "🎁 Обменять алмазики")
async def exchange_button(message: Message) -> None:
    """Show exchange options."""
    user = User.get_or_none(User.user_id == message.from_user.id)
    if not user:
        await message.answer("Сначала начните работу с ботом через /start")
        return

    balance = int(user.balance)
    gifts = list(Gift.select().where(Gift.is_active == True))
    text = (
        f"💎 <b>Обмен алмазов</b>\n\n"
        f"✨ <b>Ваш баланс:</b> {balance} 💎\n\n"
        "‼️ <b>Условия обмена:</b>\n"
        "• ✅ Выполнить <b>10 заданий</b>\n"
        "• ✅ Пригласить <b>3 реферала</b>\n\n"
        "🔍 После первого обмена — условия больше не требуются!\n\n"
        "🎁 Выберите подарок для обмена:"
    )
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=dynamic_gifts_keyboard(gifts)
    )


@router.message(F.text == "💎 Пополнить алмазы")
async def topup_button(message: Message) -> None:
    """Show top-up methods."""
    await message.answer(
        "💳 <b>Пополнение алмазов</b>\n\n"
        "Способы оплаты:\n"
        "• 💸 СБП (Сбербанк)\n"
        "• 🪙 USDT (TRC20)\n"
        "• 🎁 Промокод\n\n"
        "Напишите @support_bot для оформления заказа",
        parse_mode="HTML"
    )


@router.message(F.text == "💬 Наш канал")
async def channel_button(message: Message) -> None:
    """Send channel link with proper formatting."""
    await message.answer(
        "💬 Официальный канал: https://t.me/lorus_diamond\n\n"
        "Там публикуются:\n"
        "• Новые задания и акции\n"
        "• Результаты розыгрышей\n"
        "• Эксклюзивные подарки для подписчиков",
        disable_web_page_preview=True
    )


@router.message(F.text == "❓ Помощь")
async def help_button(message: Message) -> None:
    """Show help information."""
    help_text = (
        "❓ <b>Помощь</b>\n\n"
        "👋 Привет! Ты в боте по заработку звезд.\n\n"
        "🎯 <b>Как это работает:</b>\n"
        "• ✅ Выполняй задания — получай алмазы 💎\n"
        "• 🤝 Приглашай друзей — зарабатывай 10% от их наград\n"
        "• 🎰 Играй в мини-игры — выигрывай больше алмазов\n"
        "• 🎁 Обменивай алмазы на реальные подарки\n\n"
        "💡 <b>Реферальная система:</b>\n"
        "• Когда твой реферал выполнит 3 задания, он станет активным\n"
        "• Ты получишь 3 💎 за его активацию\n"
        "• Далее ты будешь получать 10% от всех его наград\n\n"
        "🎁 <b>Условия обмена:</b>\n"
        "• Выполни 10 заданий\n"
        "• Пригласи 3 реферала\n"
        "После первого обмена условия больше не требуются!\n\n"
        "📱 <b>Разделы бота:</b>\n"
        "• 🍄 Профиль — твоя статистика\n"
        "• ✅ Задания — доступные задачи\n"
        "• 📝 Добавить задание — создай свое задание\n"
        "• 🎰 Мини-игры — играй и выигрывай\n"
        "• 🎁 Обменять алмазики — получи подарки\n"
        "• 💎 Пополнить алмазы — купи больше\n\n"
        "💬 Возникли вопросы? Пиши @support_bot"
    )
    await message.answer(help_text, parse_mode="HTML")


@router.message(F.text == "🛠 Админ панель")
async def admin_button(message: Message) -> None:
    """Secure admin panel access."""
    try:
        if not is_admin(message.from_user.id):
            await message.answer("🚫 Доступ запрещён")
            logger.warning(f"Unauthorized admin access attempt by user {message.from_user.id}")
            return
    except Exception as e:
        logger.error(f"Admin check failed for {message.from_user.id}: {e}")
        await message.answer("❌ Ошибка проверки доступа")
        return
    
    from handlers.admin.keyboards import admin_keyboard
    stats = (
        f"🛠 <b>Админ-панель</b>\n\n"
        f"👥 Пользователей: {User.select().count()}\n"
        f"🆕 Сегодня: {User.select().where(User.date >= datetime.now().date()).count()}"
    )
    await message.answer(stats, reply_markup=admin_keyboard(), parse_mode="HTML")