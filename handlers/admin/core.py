"""Admin utilities and helper functions."""
import logging
from typing import Dict, Optional
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from handlers.utils import is_admin

logger = logging.getLogger(__name__)


async def safe_edit_or_answer(
    call: CallbackQuery,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    parse_mode: Optional[str] = None
) -> None:
    """Safely edit or answer message (works for both text and media)."""
    try:
        if call.message.photo:
            await call.message.edit_caption(caption=text, reply_markup=reply_markup, parse_mode=parse_mode)
        else:
            await call.message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception as e:
        logger.debug(f"Failed to edit message: {e}")
        try:
            await call.message.delete()
            await call.message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
        except Exception as e:
            logger.exception(f"Failed to delete/answer: {e}")


def format_number(n: int) -> str:
    """Format number with spaces as separator."""
    return f"{n:,}".replace(",", " ")


def back_kb() -> InlineKeyboardMarkup:
    """Back button keyboard."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin")]
    ])


def delete_keyboard(items: Dict[str, str], prefix: str) -> InlineKeyboardMarkup:
    """Generate keyboard for deleting items."""
    buttons = [
        [InlineKeyboardButton(text=text, callback_data=f"{prefix}{key}")]
        for key, text in items.items()
    ]
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
