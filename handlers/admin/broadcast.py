"""Broadcast system."""
import logging
import asyncio
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.models import User
from loader import bot
from .core import is_admin, safe_edit_or_answer, back_kb

logger = logging.getLogger(__name__)
router = Router()


class BroadcastState(StatesGroup):
    waiting_for_text = State()
    waiting_for_button = State()
    confirming = State()


@router.callback_query(F.data == "admin_broadcast")
async def start_broadcast(call: CallbackQuery, state: FSMContext):
    """Start broadcast wizard."""
    if not is_admin(call.from_user.id):
        return
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📄 Текст", callback_data="text_only"),
         InlineKeyboardButton(text="🔗 Текст+кнопка", callback_data="text_with_button")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin")]
    ])
    await safe_edit_or_answer(call, "📩 Тип рассылки:", reply_markup=kb)


@router.callback_query(F.data == "send_broadcast")
async def start_broadcast_old(call: CallbackQuery, state: FSMContext):
    """Start broadcast wizard (legacy)."""
    await start_broadcast(call, state)


@router.callback_query(F.data.in_({"text_only", "text_with_button"}))
async def broadcast_choice(call: CallbackQuery, state: FSMContext):
    """Process broadcast type choice."""
    if not is_admin(call.from_user.id):
        await call.answer("🚫 Доступ запрещён.", show_alert=True)
        return
    
    await state.update_data(broadcast_type=call.data)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="send_broadcast")]
    ])
    await safe_edit_or_answer(call, "✏️ Текст рассылки:", reply_markup=kb)
    await state.set_state(BroadcastState.waiting_for_text)


@router.message(BroadcastState.waiting_for_text)
async def receive_text(message: Message, state: FSMContext):
    """Receive broadcast text."""
    if not is_admin(message.from_user.id):
        await message.delete()
        return
    
    await state.update_data(text=message.text)
    data = await state.get_data()
    
    if data["broadcast_type"] == "text_with_button":
        await message.answer("🔗 Текст кнопки, ссылка (через запятую):", reply_markup=back_kb())
        await state.set_state(BroadcastState.waiting_for_button)
    else:
        await message.answer("✅ Напишите **Да** для отправки.", reply_markup=back_kb())
        await state.set_state(BroadcastState.confirming)
    
    await message.delete()


@router.message(BroadcastState.waiting_for_button)
async def receive_button(message: Message, state: FSMContext):
    """Receive button details."""
    if not is_admin(message.from_user.id):
        await message.delete()
        return
    
    try:
        parts = message.text.split(",", 1)
        if len(parts) != 2:
            await message.answer("❌ Формат: Текст кнопки,ссылка", reply_markup=back_kb())
            await message.delete()
            return
        
        text, url = parts
        text = text.strip()
        url = url.strip()
        
        if not text or not url:
            await message.answer("❌ Текст и ссылка не могут быть пустыми.", reply_markup=back_kb())
            await message.delete()
            return
        
        if not url.startswith(("http://", "https://")):
            await message.answer("❌ Ссылка должна начинаться с http:// или https://", reply_markup=back_kb())
            await message.delete()
            return
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=text, url=url)]
        ])
        await state.update_data(button=kb)
        await message.answer("✅ Напишите **Да** для отправки.", reply_markup=back_kb())
        await state.set_state(BroadcastState.confirming)
    except Exception as e:
        logger.exception(f"Error parsing button: {e}")
        await message.answer("❌ Ошибка обработки данных.", reply_markup=back_kb())
    
    await message.delete()


@router.message(BroadcastState.confirming)
async def confirm_broadcast(message: Message, state: FSMContext):
    """Confirm and send broadcast."""
    if not is_admin(message.from_user.id):
        await message.delete()
        return
    
    if message.text.lower() != "да":
        await message.answer("❌ Отменено.", reply_markup=back_kb())
        await state.clear()
        await message.delete()
        return
    
    data = await state.get_data()
    users = list(User.select())
    
    if not users:
        await message.answer("📭 Нет пользователей.", reply_markup=back_kb())
        await state.clear()
        await message.delete()
        return
    
    admin_id = message.from_user.id
    total = len(users)
    logger.info(f"Admin {admin_id} started broadcast to {total} users")
    
    success = fail = 0
    progress = await message.answer(f"📨 0 / {total}")
    
    for i, user in enumerate(users, 1):
        try:
            await bot.send_message(user.user_id, data["text"], reply_markup=data.get("button"))
            success += 1
        except Exception as e:
            logger.debug(f"Failed to send to {user.user_id}: {e}")
            fail += 1
        
        if i % 10 == 0 or i == total:
            await progress.edit_text(f"📨 {success} / {total}\n❌ Ошибок: {fail}")
        
        await asyncio.sleep(0.05)
    
    logger.info(f"Broadcast finished: {success} success, {fail} failed")
    await progress.edit_text(f"✅ Готово!\n✅ Успешно: {success}\n❌ Ошибок: {fail}")
    await state.clear()
    await message.delete()
