"""Admin management handlers."""
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.models import Root
from .core import is_admin, safe_edit_or_answer, back_kb, delete_keyboard

logger = logging.getLogger(__name__)
router = Router()


class ManageAdminsState(StatesGroup):
    waiting_for_add_id = State()
    waiting_for_remove_id = State()


@router.callback_query(F.data == "admin_manage_admins")
async def manage_admins_menu(call: CallbackQuery):
    """Show admin management menu."""
    if not is_admin(call.from_user.id):
        return
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить", callback_data="add_admin"),
         InlineKeyboardButton(text="❌ Удалить", callback_data="remove_admin")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin")]
    ])
    await safe_edit_or_answer(call, "🔐 Управление админами", reply_markup=kb)


@router.callback_query(F.data == "manage_admins")
async def manage_admins_menu_old(call: CallbackQuery):
    """Show admin management menu (legacy)."""
    await manage_admins_menu(call)


@router.callback_query(F.data == "add_admin")
async def add_admin_start(call: CallbackQuery, state: FSMContext):
    """Start adding new admin."""
    if not is_admin(call.from_user.id):
        return
    
    await safe_edit_or_answer(call, "🆔 Введите Telegram ID нового админа:", reply_markup=back_kb())
    await state.set_state(ManageAdminsState.waiting_for_add_id)


@router.message(ManageAdminsState.waiting_for_add_id)
async def add_admin_process(message: Message, state: FSMContext):
    """Process new admin ID."""
    if not is_admin(message.from_user.id):
        await message.delete()
        return
    
    try:
        admin_id = int(message.text.strip())
        Root.get_or_create(root_id=admin_id)
        logger.info(f"Admin {message.from_user.id} added admin {admin_id}")
        await message.answer(f"✅ Пользователь {admin_id} добавлен в админы.", reply_markup=back_kb())
    except ValueError:
        await message.answer("⚠️ Введите корректный числовой ID.", reply_markup=back_kb())
    finally:
        await state.clear()
        await message.delete()


@router.callback_query(F.data == "remove_admin")
async def remove_admin_start(call: CallbackQuery, state: FSMContext):
    """Start removing admin."""
    if not is_admin(call.from_user.id):
        return
    
    admins = list(Root.select())
    if len(admins) <= 1:
        await call.answer("❌ Нельзя удалить последнего админа.", show_alert=True)
        return
    
    admin_map = {str(a.root_id): str(a.root_id) for a in admins}
    keyboard = delete_keyboard(admin_map, prefix="deladmin_")
    await safe_edit_or_answer(call, "🗑 Выберите админа для удаления:", reply_markup=keyboard)


@router.callback_query(F.data.startswith("deladmin_"))
async def confirm_remove_admin(call: CallbackQuery):
    """Delete selected admin."""
    if not is_admin(call.from_user.id):
        return
    
    try:
        admin_id = int(call.data.split("_", 1)[1])
        
        if admin_id == call.from_user.id:
            await call.answer("❌ Нельзя удалить самого себя.", show_alert=True)
            return
        
        Root.delete().where(Root.root_id == admin_id).execute()
        logger.info(f"Admin {call.from_user.id} removed admin {admin_id}")
        await call.answer(f"✅ Админ {admin_id} удалён.", show_alert=True)
        await manage_admins_menu(call)
    except Exception as e:
        logger.exception(f"Error removing admin: {e}")
        await call.answer("❌ Ошибка при удалении.", show_alert=True)
