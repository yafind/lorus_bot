from typing import List, Optional

from aiogram.types import ReplyKeyboardMarkup, InlineKeyboardMarkup, KeyboardButton, InlineKeyboardButton, WebAppInfo
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

from database.models import Gift

BTN_PROFILE = "🍄 Профиль"
BTN_TASKS = "✅ Задания"
BTN_ADD_TASK = "📝 Добавить задание"
BTN_MINIGAMES = "🎰 Мини-игры"
BTN_EXCHANGE = "🎁 Обменять алмазики"
BTN_TOP_UP = "💎 Пополнить алмазы"
BTN_CHANNEL = "💬 Наш канал"
BTN_HELP = "❓ Помощь"
BTN_ADMIN_PANEL = "🛠 Админ панель"
BTN_MINI_APP = "📱 Mini App"

BTN_BACK = "🔙 Назад"
BTN_NO_GIFTS = "🎁 Подарков пока нет"
BTN_HIDE_REF_REWARD = "🔺 Скрыть награду от рефералов"
BTN_SHOW_REF_REWARD = "🔻 Открыть награду от рефералов"


def start_keyboard(is_admin: bool = False, mini_app_url: Optional[str] = None) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    
    builder.row(
        KeyboardButton(text=BTN_PROFILE),
        KeyboardButton(text=BTN_TASKS)
    )
    builder.row(
        KeyboardButton(text=BTN_ADD_TASK),
        KeyboardButton(text=BTN_MINIGAMES)
    )
    builder.row(
        KeyboardButton(text=BTN_EXCHANGE),
        KeyboardButton(text=BTN_TOP_UP)
    )
    builder.row(
        KeyboardButton(text=BTN_CHANNEL),
        KeyboardButton(text=BTN_HELP)
    )

    if mini_app_url:
        builder.row(
            KeyboardButton(text=BTN_MINI_APP, web_app=WebAppInfo(url=mini_app_url))
        )
    else:
        builder.row(KeyboardButton(text=BTN_MINI_APP))
    
    if is_admin:
        builder.row(KeyboardButton(text=BTN_ADMIN_PANEL))
    
    return builder.as_markup(resize_keyboard=True)


def minigame_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(text="🎲 Кубик", callback_data="play_dice"),
        InlineKeyboardButton(text="🏀 Баскетбол", callback_data="play_basketball")
    )
    builder.row(
        InlineKeyboardButton(text="⚽ Футбол", callback_data="play_football"),
        InlineKeyboardButton(text="🎯 Дартс", callback_data="play_dart")
    )
    builder.row(
        InlineKeyboardButton(text="🎳 Боулинг", callback_data="play_bowling"),
        InlineKeyboardButton(text="🎰 Слоты", callback_data="play_slot_machine")
    )
    
    return builder.as_markup()


def admin_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    builder.add(InlineKeyboardButton(text="🧩 Управление заданиями", callback_data="admin_manage_tasks"))
    builder.add(InlineKeyboardButton(text="🎁 Управление подарками", callback_data="admin_manage_gifts"))
    builder.add(InlineKeyboardButton(text="🔐 Управление админами", callback_data="admin_manage_admins"))
    builder.add(InlineKeyboardButton(text="📣 Рассылка", callback_data="admin_broadcast"))
    builder.add(InlineKeyboardButton(text="💰 Изменить баланс", callback_data="admin_change_balance"))
    builder.add(InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"))

    return builder.as_markup()


def topup_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text=BTN_BACK))
    return builder.as_markup(resize_keyboard=True)


def toggle_ref_reward_keyboard(is_showing: bool = False) -> InlineKeyboardMarkup:

    builder = InlineKeyboardBuilder()
    
    button_text = BTN_HIDE_REF_REWARD if is_showing else BTN_SHOW_REF_REWARD
    builder.button(text=button_text, callback_data="toggle_ref_rewards")
    
    return builder.as_markup()


def dynamic_gifts_keyboard(gifts: List[Gift], max_buttons: int = 20) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    if not gifts:
        builder.row(InlineKeyboardButton(text=BTN_NO_GIFTS, callback_data="no_gifts"))
        builder.row(InlineKeyboardButton(text=BTN_BACK, callback_data="exchange_back"))
        return builder.as_markup()
    
    limited_gifts = gifts[:max_buttons]
    
    # Добавляем кнопки по 2 в ряд (2 столбика)
    for i in range(0, len(limited_gifts), 2):
        row_buttons = []
        
        # Первая кнопка (левая)
        gift = limited_gifts[i]
        row_buttons.append(InlineKeyboardButton(
            text=f"💎 {gift.diamond_cost} — {_truncate_text(gift.display_name, 16)}",
            callback_data=f"gift:{gift.id}"
        ))
        
        # Вторая кнопка (правая), если существует
        if i + 1 < len(limited_gifts):
            gift = limited_gifts[i + 1]
            row_buttons.append(InlineKeyboardButton(
                text=f"💎 {gift.diamond_cost} — {_truncate_text(gift.display_name, 16)}",
                callback_data=f"gift:{gift.id}"
            ))
        
        builder.row(*row_buttons)
    
    # Кнопка назад в отдельной строке
    builder.row(InlineKeyboardButton(text=BTN_BACK, callback_data="exchange_back"))
    
    return builder.as_markup()


def _truncate_text(text: str, max_length: int) -> str:
    return text if len(text) <= max_length else f"{text[:max_length - 1]}…"


def back_button_keyboard(callback_data: str = "exchange_stars") -> InlineKeyboardMarkup:
    """Инлайн-клавиатура с кнопкой 'Назад'."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Назад", callback_data=callback_data)
    return builder.as_markup()