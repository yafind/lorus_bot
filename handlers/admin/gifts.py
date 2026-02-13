"""Gift management handlers."""
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.models import Gift
from .core import is_admin, safe_edit_or_answer, back_kb, delete_keyboard

logger = logging.getLogger(__name__)
router = Router()


class AddGiftState(StatesGroup):
    display_name = State()
    diamond_cost = State()


@router.callback_query(F.data == "admin_manage_gifts")
async def manage_gifts_menu(call: CallbackQuery):
    """Show gift management menu."""
    if not is_admin(call.from_user.id):
        return
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить", callback_data="add_gift"),
         InlineKeyboardButton(text="❌ Удалить", callback_data="delete_gift")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin")]
    ])
    await safe_edit_or_answer(call, "🎁 Управление подарками", reply_markup=kb)


@router.callback_query(F.data == "manage_gifts")
async def manage_gifts_menu_old(call: CallbackQuery):
    """Show gift management menu (legacy)."""
    await manage_gifts_menu(call)


@router.callback_query(F.data == "delete_gift")
async def delete_gift_handler(call: CallbackQuery):
    """Show gift list for deletion."""
    if not is_admin(call.from_user.id):
        return
    
    gifts = list(Gift.select().where(Gift.is_active == True))
    if not gifts:
        await safe_edit_or_answer(call, "📭 Нет подарков.", reply_markup=back_kb())
        return
    
    gift_map = {str(g.id): f"{g.display_name} ({g.diamond_cost} 💎)" for g in gifts}
    keyboard = delete_keyboard(gift_map, prefix="delgift_")
    await safe_edit_or_answer(call, "🗑 Выберите подарок:", reply_markup=keyboard)


@router.callback_query(F.data.startswith("delgift_"))
async def confirm_delete_gift(call: CallbackQuery):
    """Delete selected gift."""
    if not is_admin(call.from_user.id):
        return
    
    try:
        gift_id = int(call.data.split("_")[1])
        gift = Gift.get_by_id(gift_id)
        gift.delete_instance()
        logger.info(f"Admin {call.from_user.id} deleted gift {gift_id}")
        await call.answer("✅ Удалено!", show_alert=True)
        await delete_gift_handler(call)
    except Exception as e:
        logger.exception(f"Error deleting gift: {e}")
        await call.answer("❌ Ошибка при удалении.", show_alert=True)
        await delete_gift_handler(call)


@router.callback_query(F.data == "add_gift")
async def add_gift_start(call: CallbackQuery, state: FSMContext):
    """Start adding new gift."""
    if not is_admin(call.from_user.id):
        return
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="manage_gifts")]
    ])
    await safe_edit_or_answer(call, "🎁 Название подарка:", reply_markup=kb)
    await state.set_state(AddGiftState.display_name)


@router.message(AddGiftState.display_name)
async def process_gift_name(message: Message, state: FSMContext):
    """Process gift name."""
    if not is_admin(message.from_user.id):
        await message.delete()
        return
    
    await state.update_data(display_name=message.text.strip())
    await message.answer("💎 Стоимость в алмазах:", reply_markup=back_kb())
    await state.set_state(AddGiftState.diamond_cost)
    await message.delete()


@router.message(AddGiftState.diamond_cost)
async def process_gift_cost(message: Message, state: FSMContext):
    """Process gift cost."""
    if not is_admin(message.from_user.id):
        await message.delete()
        return
    
    try:
        cost = int(message.text.strip())
        if cost <= 0:
            raise ValueError
        
        data = await state.get_data()
        name = data["display_name"]
        
        # Generate internal name
        internal = "".join(c.lower() for c in name if c.isalnum() or c in " _-").replace(" ", "_")[:60] or f"gift_{cost}"
        
        # Handle duplicates
        counter = 1
        orig = internal
        while Gift.select().where(Gift.internal_name == internal).exists():
            internal = f"{orig}_{counter}"
            counter += 1
        
        try:
            gift = Gift.create(
                internal_name=internal,
                display_name=name,
                diamond_cost=cost,
                is_active=True
            )
            logger.info(f"Admin {message.from_user.id} added gift: {name} ({cost} 💎)")
            await message.answer(f"✅ Подарок добавлен!\n{name} — {cost} 💎", reply_markup=back_kb())
        except Exception as e:
            logger.exception(f"Error creating gift: {e}")
            await message.answer("❌ Подарок с таким названием уже существует.", reply_markup=back_kb())
        
        await state.clear()
    except ValueError:
        await message.answer("❌ Введите положительное целое число.", reply_markup=back_kb())
    
    await message.delete()
