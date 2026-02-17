"""Main menu handlers."""
import logging
from html import escape
from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from config import MINI_APP_URL
from database.models import User, Gift
from keyboards.keyboard import toggle_ref_reward_keyboard, minigame_keyboard, dynamic_gifts_keyboard
from handlers.tasks.tasks_view import show_tasks_from_message
from handlers.tasks.add_task import add_task_start
from handlers.profile import build_profile_text_simple

logger = logging.getLogger(__name__)
router = Router()


@router.message(F.text == "✅ Задания")
async def tasks_button(message: Message, state: FSMContext) -> None:
    """Handle tasks button with proper state management."""
    try:
        await show_tasks_from_message(message, state)
    except Exception as e:
        logger.exception(f"Error loading tasks for user {message.from_user.id}: {e}")
        await message.answer("⚠️ Ошибка при загрузке заданий. Попробуйте позже.")


@router.message(F.text == "🍄 Профиль")
async def profile_button(message: Message) -> None:
    """Show detailed user profile with stats."""
    try:
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
    await state.clear()
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
        "Напишите @supStarsbot для оформления заказа",
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
        "💬 Возникли вопросы? Пиши @supStarsbot"
    )
    await message.answer(help_text, parse_mode="HTML")


@router.message(F.text == "📱 Mini App")
async def mini_app_button(message: Message) -> None:
    """Fallback handler for Mini App button without WebApp URL."""
    if MINI_APP_URL:
        await message.answer(f"Открой Mini App по ссылке: {MINI_APP_URL}")
        return
    await message.answer(
        "Mini App пока не настроен.\n"
        "Добавьте MINI_APP_URL в .env (HTTPS-ссылка), затем перезапустите бота."
    )
