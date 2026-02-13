"""Admin panel main handler."""
import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message
from database.models import User
from handlers.utils import is_admin
from handlers.admin.keyboards import admin_keyboard

logger = logging.getLogger(__name__)
router = Router()


@router.message(F.text == "🛠 Админ панель")
async def admin_panel_button(message: Message) -> None:
    """Secure admin panel access."""
    if not is_admin(message.from_user.id):
        await message.answer("🚫 Доступ запрещён")
        logger.warning(f"Unauthorized admin access attempt by user {message.from_user.id}")
        return
    
    stats = (
        f"🛠 <b>Админ-панель</b>\n\n"
        f"👥 Пользователей: {User.select().count()}\n"
        f"🆕 Сегодня: {User.select().where(User.date >= datetime.now().date()).count()}"
    )
    await message.answer(stats, reply_markup=admin_keyboard(), parse_mode="HTML")
