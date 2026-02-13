"""Admin keyboards."""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def admin_keyboard() -> InlineKeyboardMarkup:
    """Main admin panel keyboard."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton(text="🧩 Управление заданиями", callback_data="manage_tasks")],
        [InlineKeyboardButton(text="🎁 Управление подарками", callback_data="manage_gifts")],
        [InlineKeyboardButton(text="🔐 Управление админами", callback_data="manage_admins")],
        [InlineKeyboardButton(text="💰 Изменить баланс", callback_data="edit_balance")],
        [InlineKeyboardButton(text="📣 Рассылка", callback_data="send_broadcast")],
    ])
