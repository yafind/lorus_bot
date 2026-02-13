"""Task management handlers."""
import logging
import re
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.models import Task
from .core import is_admin, safe_edit_or_answer, back_kb, delete_keyboard

logger = logging.getLogger(__name__)
router = Router()


class AddTaskState(StatesGroup):
    invite_link = State()
    chat_id = State()
    reward = State()


@router.callback_query(F.data == "admin_manage_tasks")
async def manage_tasks_menu(call: CallbackQuery):
    """Show task management menu."""
    if not is_admin(call.from_user.id):
        return
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить", callback_data="add_task"),
         InlineKeyboardButton(text="❌ Удалить", callback_data="delete_task")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin")]
    ])
    await safe_edit_or_answer(call, "🧩 Управление заданиями", reply_markup=kb)


@router.callback_query(F.data == "manage_tasks")
async def manage_tasks_menu_old(call: CallbackQuery):
    """Show task management menu (legacy)."""
    await manage_tasks_menu(call)


@router.callback_query(F.data == "delete_task")
async def delete_task_handler(call: CallbackQuery):
    """Show task list for deletion."""
    if not is_admin(call.from_user.id):
        return
    
    tasks = list(Task.select())
    if not tasks:
        await safe_edit_or_answer(call, "📭 Нет заданий.", reply_markup=back_kb())
        return
    
    task_map = {str(t.id): f"{t.invite_link} ({t.reward} 💎)" for t in tasks}
    keyboard = delete_keyboard(task_map, prefix="delete_channel_")
    await safe_edit_or_answer(call, "🗑 Выберите задание:", reply_markup=keyboard)


@router.callback_query(F.data.startswith("delete_channel_"))
async def confirm_delete_task(call: CallbackQuery):
    """Delete selected task."""
    if not is_admin(call.from_user.id):
        return
    
    try:
        task_id = int(call.data.split("_")[-1])
        task = Task.get_by_id(task_id)
        task.delete_instance()
        logger.info(f"Admin {call.from_user.id} deleted task {task_id}")
        await call.answer("✅ Удалено!", show_alert=True)
        await delete_task_handler(call)
    except Exception as e:
        logger.exception(f"Error deleting task: {e}")
        await call.answer("❌ Ошибка при удалении.", show_alert=True)
        await delete_task_handler(call)


@router.callback_query(F.data == 'add_task')
async def add_task_handler(call: CallbackQuery, state: FSMContext):
    """Start adding new task."""
    if not is_admin(call.from_user.id):
        return
    
    await safe_edit_or_answer(call, "🔗 Ссылка-инвайт (https://t.me/+...):", reply_markup=back_kb())
    await state.set_state(AddTaskState.invite_link)


@router.message(AddTaskState.invite_link)
async def process_invite_link(message: Message, state: FSMContext):
    """Process invite link."""
    if not is_admin(message.from_user.id):
        await message.delete()
        return
    
    link = message.text.strip()
    if not re.match(r"^https://t\.me/\+[a-zA-Z0-9_-]+$", link):
        await message.answer("❌ Неверный формат ссылки.", reply_markup=back_kb())
        await message.delete()
        return
    
    await state.update_data(invite_link=link)
    await message.answer("🆔 ID канала (-100...):", reply_markup=back_kb())
    await state.set_state(AddTaskState.chat_id)
    await message.delete()


@router.message(AddTaskState.chat_id)
async def process_chat_id(message: Message, state: FSMContext):
    """Process channel ID."""
    if not is_admin(message.from_user.id):
        await message.delete()
        return
    
    try:
        chat_id = int(message.text.strip())
        if chat_id > 0:
            raise ValueError("ID должен быть отрицательным")
        if not str(chat_id).startswith("-100"):
            raise ValueError("Неверный формат ID")
        
        await state.update_data(chat_id=chat_id)
        await message.answer("💎 Награда (целое число):", reply_markup=back_kb())
        await state.set_state(AddTaskState.reward)
    except (ValueError, OverflowError):
        await message.answer("❌ Неверный ID канала (-100...).", reply_markup=back_kb())
    
    await message.delete()


@router.message(AddTaskState.reward)
async def process_reward(message: Message, state: FSMContext):
    """Process reward amount."""
    if not is_admin(message.from_user.id):
        await message.delete()
        return
    
    try:
        reward = int(message.text.strip())
        if reward <= 0:
            raise ValueError
        
        data = await state.get_data()
        task = Task.create(
            invite_link=data["invite_link"],
            chat_id=data["chat_id"],
            reward=reward,
            is_active=True
        )
        logger.info(f"Admin {message.from_user.id} added task {task.id}: {data['invite_link']}")
        
        await message.answer(
            f"✅ Задание добавлено!\nСсылка: {data['invite_link']}\nНаграда: {reward} 💎",
            reply_markup=back_kb()
        )
        await state.clear()
    except ValueError:
        await message.answer("❌ Награда — положительное целое число.", reply_markup=back_kb())
    
    await message.delete()
