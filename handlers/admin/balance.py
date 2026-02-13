"""User balance management."""
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.models import User
from .core import is_admin, safe_edit_or_answer, back_kb

logger = logging.getLogger(__name__)
router = Router()


class SearchUserState(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_star_change = State()


@router.callback_query(F.data == 'admin_change_balance')
async def start_edit_balance(call: CallbackQuery, state: FSMContext):
    """Start balance edit process."""
    if not is_admin(call.from_user.id):
        await call.answer("🚫 Доступ запрещён.", show_alert=True)
        return
    
    await safe_edit_or_answer(call, "🆔 Введите ID пользователя:", reply_markup=back_kb())
    await state.set_state(SearchUserState.waiting_for_user_id)


@router.callback_query(F.data == 'edit_balance')
async def start_edit_balance_old(call: CallbackQuery, state: FSMContext):
    """Start balance edit process (legacy)."""
    await start_edit_balance(call, state)


@router.message(SearchUserState.waiting_for_user_id)
async def process_user_id(message: Message, state: FSMContext):
    """Process user ID input."""
    if not is_admin(message.from_user.id):
        await message.delete()
        return
    
    try:
        user_id = int(message.text)
        user = User.get_or_none(User.user_id == user_id)
        
        if user:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="⬇️ Снизить", callback_data=f"change_diamonds_{user_id}_decrease"),
                    InlineKeyboardButton(text="⬆️ Повысить", callback_data=f"change_diamonds_{user_id}_increase")
                ],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin")]
            ])
            await message.answer(f"👤 ID: {user_id}\n💰 Баланс: {int(user.balance)} 💎", reply_markup=kb)
        else:
            await message.answer("❌ Пользователь не найден.", reply_markup=back_kb())
        
        await state.clear()
    except ValueError:
        await message.answer("⚠️ Введите числовой ID.", reply_markup=back_kb())
    finally:
        await message.delete()


@router.callback_query(F.data.startswith("change_diamonds_"))
async def change_diamonds(call: CallbackQuery, state: FSMContext):
    """Start diamond change process."""
    if not is_admin(call.from_user.id):
        await call.answer("🚫 Доступ запрещён.", show_alert=True)
        return
    
    parts = call.data.split("_")
    if len(parts) != 4:
        await call.answer("⚠️ Ошибка данных.", show_alert=True)
        return
    
    try:
        user_id = int(parts[2])
        action = parts[3]
    except ValueError:
        await call.answer("⚠️ Ошибка данных.", show_alert=True)
        return
    
    user = User.get_or_none(User.user_id == user_id)
    if not user:
        await call.answer("❌ Пользователь не найден.", show_alert=True)
        return
    
    await state.update_data(user_id=user_id, action=action)
    text = "⬆️ На сколько увеличить?" if action == "increase" else "⬇️ На сколько уменьшить?"
    await safe_edit_or_answer(call, text, reply_markup=back_kb())
    await state.set_state(SearchUserState.waiting_for_star_change)


@router.message(SearchUserState.waiting_for_star_change)
async def process_diamond_change(message: Message, state: FSMContext):
    """Process diamond change amount."""
    if not is_admin(message.from_user.id):
        await message.delete()
        return
    
    try:
        diamonds = int(float(message.text.replace(",", ".")))
    except ValueError:
        await message.answer("⚠️ Введите число.", reply_markup=back_kb())
        await message.delete()
        return
    
    data = await state.get_data()
    user_id = data.get("user_id")
    action = data.get("action")
    user = User.get_or_none(User.user_id == user_id)
    
    if not user:
        await message.answer("❌ Пользователь не найден.", reply_markup=back_kb())
        await state.clear()
        await message.delete()
        return
    
    old_balance = user.balance
    if action == "increase":
        user.balance += diamonds
    else:
        user.balance = max(0, user.balance - diamonds)
    
    user.save()
    logger.info(
        f"Admin {message.from_user.id} changed balance for {user_id}: "
        f"{old_balance} -> {user.balance} ({action} {diamonds})"
    )
    
    await message.answer(
        f"✅ Баланс обновлён!\nID: {user_id}\nНовый баланс: {int(user.balance)} 💎",
        reply_markup=back_kb()
    )
    
    await state.clear()
    await message.delete()
