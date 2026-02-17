import asyncio
import logging
from aiogram import F, Router
from aiogram.types import CallbackQuery, Message, User as TgUser
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.enums.dice_emoji import DiceEmoji
from aiogram.exceptions import TelegramAPIError

from database.models import User
from loader import bot
from config import chat_game
from keyboards.keyboard import minigame_keyboard, back_button_keyboard

router = Router()
logger = logging.getLogger(__name__)


class MiniGameStates(StatesGroup):
    playing = State()


# Конфигурация игр: (эмодзи, условие победы, выплата, название)
GAME_CONFIG = {
    "dice": (DiceEmoji.DICE, lambda v: v >= 5, 12, "Кубик"),
    "basketball": (DiceEmoji.BASKETBALL, lambda v: v >= 4, 10, "Баскетбол"),
    "football": (DiceEmoji.FOOTBALL, lambda v: v >= 3, 8, "Футбол"),
    "dart": (DiceEmoji.DART, lambda v: v == 6, 25, "Дартс"),
    "bowling": (DiceEmoji.BOWLING, lambda v: v == 6, 25, "Боулинг"),
    "slot_machine": (DiceEmoji.SLOT_MACHINE, lambda v: v == 64, 150, "Слоты"),
}


@router.callback_query(F.data == "minigame")
async def minigame_menu(call: CallbackQuery):
    """Меню выбора мини-игр"""
    user = User.get_or_none(User.user_id == call.from_user.id)
    if not user:
        await call.answer("❌ Сначала начните диалог с ботом.", show_alert=True)
        return

    text = (
        f"🎮 <b>Мини-игры</b>\n"
        f"💰 Баланс: {int(user.balance)} 💎\n\n"
        f"Стоимость игры: <b>5 💎</b>\n"
        f"Выберите игру ниже:"
    )

    try:
        await call.message.edit_text(text, reply_markup=minigame_keyboard(), parse_mode="HTML")
    except TelegramAPIError:
        await call.message.answer(text, reply_markup=minigame_keyboard(), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data.startswith("play_"))
async def start_minigame(call: CallbackQuery, state: FSMContext):
    """Запуск мини-игры"""
    game_key = call.data.removeprefix("play_")
    await launch_minigame(call.message, call.from_user, state, game_key)
    await call.answer()


async def launch_minigame(message: Message, tg_user: TgUser, state: FSMContext, game_key: str) -> None:
    """Общий запуск мини-игры из callback и Mini App."""
    # Блокировка параллельных запусков
    if await state.get_state() == MiniGameStates.playing.state:
        await message.answer("⏳ Игра уже запущена!")
        return

    if game_key not in GAME_CONFIG:
        await message.answer("❌ Игра не найдена.")
        return

    emoji, win_condition, payout, game_name = GAME_CONFIG[game_key]

    # Списание ставки (атомарная операция)
    if not User.update(balance=User.balance - 5).where(
        (User.user_id == tg_user.id) & (User.balance >= 5)
    ).execute():
        await message.answer("❌ Недостаточно 💎 для ставки!")
        return

    await state.set_state(MiniGameStates.playing)

    try:
        # Отправка анимации
        dice_msg = await message.answer_dice(emoji=emoji)
        await asyncio.sleep(2.5)

        # Обработка результата
        if not dice_msg.dice:
            # Возврат ставки при ошибке
            User.update(balance=User.balance + 5).where(User.user_id == tg_user.id).execute()
            await message.answer("⚠️ Ошибка игры. Ставка возвращена.")
            return

        value = dice_msg.dice.value
        reward = payout if win_condition(value) else 0

        # Начисление выигрыша
        if reward:
            User.update(balance=User.balance + reward).where(User.user_id == tg_user.id).execute()

        # Результат игры
        result = f"✅ <b>ПОБЕДА!</b>\n+{reward} 💎" if reward else "❌ <b>Проигрыш.</b>"
        await message.answer(
            f"🎲 {game_name}\nЗначение: <b>{value}</b>\n{result}",
            parse_mode="HTML"
        )

        # Логирование
        username = tg_user.username or "—"
        full_name = tg_user.full_name or "—"
        log_text = (
            f"🎲 <b>{game_name}</b>\n"
            f"👤 <a href='tg://user?id={tg_user.id}'>{full_name}</a> (@{username})\n"
            f"💎 Ставка: 5 → Выплата: {reward}\n"
            f"Значение: {value} → {'ПОБЕДА' if reward else 'ПРОИГРЫШ'}"
        )
        try:
            await bot.send_message(chat_game, log_text, parse_mode="HTML")
        except Exception as e:
            logger.warning(f"Ошибка логирования игры: {e}")

    finally:
        await state.clear()