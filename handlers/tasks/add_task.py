"""Local task creation handler with inline navigation."""
import logging

from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from peewee import fn

from config import TASK_LOG_CHAT_ID
from database.models import User, Task, db
from loader import bot
from handlers.tasks.states import AddTask

logger = logging.getLogger(__name__)
router = Router()

PER_PERSON_COST = 3
LOCAL_TASK_REWARD = 2


def back_inline_keyboard() -> InlineKeyboardMarkup:
    """Create inline back button."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="cancel_task_creation")]
    ])


@router.callback_query(F.data == "cancel_task_creation")
async def cancel_add_task(callback: CallbackQuery, state: FSMContext) -> None:
    """Cancel task creation via inline button."""
    # Get current state to handle refunds if needed
    current_state = await state.get_state()
    
    await state.clear()
    await callback.answer()
    
    try:
        # Return to main menu
        from keyboards.keyboard import start_keyboard
        from database.models import Root
        
        user_id = callback.from_user.id
        is_admin = Root.get_or_none(Root.root_id == user_id) is not None
        
        await callback.message.edit_text(
            "❌ Создание задания отменено. Возврат в главное меню...",
            reply_markup=None
        )
        await callback.message.answer(
            "👋 Выберите действие:",
            reply_markup=start_keyboard(is_admin=is_admin)
        )
    except (TelegramBadRequest, TelegramForbiddenError):
        try:
            from keyboards.keyboard import start_keyboard
            from database.models import Root
            
            user_id = callback.from_user.id
            is_admin = Root.get_or_none(Root.root_id == user_id) is not None
            
            await callback.message.delete()
            await callback.message.answer(
                "👋 Выберите действие:",
                reply_markup=start_keyboard(is_admin=is_admin)
            )
        except Exception:
            pass


@router.message(F.text == "📝 Добавить задание")
async def add_task_start(message: Message, state: FSMContext) -> None:
    """Start task creation FSM with clean interface."""
    # Clear any previous keyboards
    await message.answer(
        "⏳ Инициализация...",
        reply_markup=ReplyKeyboardRemove()
    )
    
    text = (
        "📝 <b>Инструкция по добавлению локального задания:</b>\n\n"
        "1️⃣ Добавьте бота в администраторы вашего канала\n"
        "2️⃣ Отправьте ссылку на канал:\n"
        "   • https://t.me/your_channel\n"
        "   • @your_channel\n"
        "3️⃣ Укажите целевое количество участников (числом)\n\n"
        f"💎 Стоимость: {PER_PERSON_COST} алмазов за 1 человека "
        "(списание происходит после подтверждения)"
    )

    await message.answer(
        text=text,
        reply_markup=back_inline_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(AddTask.waiting_for_channel)


def _extract_channel_id(text: str) -> str | None:
    """Extract channel username from URL or handle."""
    text = text.strip().split('?')[0].rstrip('/ ')
    
    if 't.me/' in text:
        username = text.split('t.me/')[-1].split('/')[0].strip()
        return username if username else None
    
    username = text.lstrip('@').split('/')[0].strip()
    return username or None


async def _check_bot_admin_rights(chat_id: int) -> tuple[bool, str]:
    """Verify bot has admin rights in chat. Returns (is_valid, error_message)."""
    try:
        me = await bot.get_me()
        member = await bot.get_chat_member(chat_id, me.id)
        
        if member.status in ("administrator", "creator"):
            return True, ""
        return False, "🔒 Бот не является администратором канала. Добавьте бота в админы."
    
    except TelegramBadRequest as e:
        if "CHAT_NOT_FOUND" in str(e):
            return False, "🔍 Канал не найден. Убедитесь, что он публичный и ссылка верна."
        elif "USER_NOT_PARTICIPANT" in str(e):
            return False, "🤖 Бот не добавлен в канал. Сначала добавьте бота, затем назначьте админом."
        return False, "⚠️ Ошибка Telegram API. Проверьте ссылку и повторите попытку."
    except Exception as e:
        return False, f"⚠️ Не удалось проверить права: {str(e)[:50]}"


@router.message(AddTask.waiting_for_channel)
async def process_channel_link(message: Message, state: FSMContext) -> None:
    """Process channel link input with validation."""
    # Check if user wants to cancel
    if message.text and "отмена" in message.text.lower():
        from keyboards.keyboard import start_keyboard
        from database.models import Root
        
        await state.clear()
        is_admin = Root.get_or_none(Root.root_id == message.from_user.id) is not None
        await message.answer(
            "❌ Создание задания отменено.",
            reply_markup=start_keyboard(is_admin=is_admin)
        )
        return
    
    if not message.text:
        await message.answer(
            "⚠️ Отправьте текстовую ссылку на канал",
            reply_markup=back_inline_keyboard()
        )
        return

    # Try to delete user message for cleaner interface
    try:
        await message.delete()
    except Exception:
        pass

    ident = _extract_channel_id(message.text)
    if not ident:
        await message.answer(
            "❗ Неверный формат ссылки.\n"
            "Примеры правильных ссылок:\n"
            "• https://t.me/example\n"
            "• @example",
            reply_markup=back_inline_keyboard()
        )
        return

    chat_ref = f"@{ident}"
    try:
        chat = await bot.get_chat(chat_ref)
        
        # Additional validation for channels
        if chat.type not in ("channel", "supergroup"):
            await message.answer(
                "❗ Это не канал/супергруппа. Отправьте ссылку на канал.",
                reply_markup=back_inline_keyboard()
            )
            return
            
    except TelegramBadRequest as e:
        if "CHAT_NOT_FOUND" in str(e):
            await message.answer(
                "🔍 Канал не найден. Убедитесь, что он публичный и ссылка верна.",
                reply_markup=back_inline_keyboard()
            )
        else:
            await message.answer(
                "⚠️ Ошибка Telegram API. Проверьте ссылку и повторите попытку.",
                reply_markup=back_inline_keyboard()
            )
        return
    except Exception:
        await message.answer(
            "⚠️ Не удалось получить информацию о канале. Попробуйте позже.",
            reply_markup=back_inline_keyboard()
        )
        return

    # Check bot admin rights
    is_valid, error_msg = await _check_bot_admin_rights(chat.id)
    if not is_valid:
        await message.answer(error_msg, reply_markup=back_inline_keyboard())
        return

    # Check for existing active task
    existing_task = Task.get_or_none(
        (Task.chat_id == chat.id) & 
        (Task.is_active == True)
    )
    if existing_task:
        owner = existing_task.owner_id
        await message.answer(
            f"ℹ️ Для этого канала уже существует активное задание (владелец: {owner}).",
            reply_markup=back_inline_keyboard()
        )
        await state.clear()
        return

    # Save channel data
    await state.update_data(invite_link=message.text.strip(), chat_id=chat.id)
    await state.set_state(AddTask.waiting_for_sub_count)
    
    await message.answer(
        "✅ Канал подтверждён.\n"
        f"Укажите целевое количество участников (минимум 10):\n"
        f"<i>Пример: 100</i>",
        reply_markup=back_inline_keyboard(),
        parse_mode="HTML"
    )


@router.message(AddTask.waiting_for_sub_count)
async def process_sub_count(message: Message, state: FSMContext) -> None:
    """Process target subscribers count with balance validation."""
    # Check if user wants to cancel
    if message.text and "отмена" in message.text.lower():
        from keyboards.keyboard import start_keyboard
        from database.models import Root
        
        await state.clear()
        is_admin = Root.get_or_none(Root.root_id == message.from_user.id) is not None
        await message.answer(
            "❌ Создание задания отменено.",
            reply_markup=start_keyboard(is_admin=is_admin)
        )
        return
    
    if not message.text:
        await message.answer(
            "⚠️ Отправьте число участников",
            reply_markup=back_inline_keyboard()
        )
        return

    # Try to delete user message
    try:
        await message.delete()
    except Exception:
        pass

    # Get user with atomic lock to prevent race conditions
    try:
        user = User.select().where(User.user_id == message.from_user.id).for_update().get()
    except User.DoesNotExist:
        await message.answer(
            "❌ Профиль не найден. Напишите /start",
            reply_markup=back_inline_keyboard()
        )
        await state.clear()
        return

    # Validate number
    try:
        target = int(message.text.strip())
        if target < 10:
            await message.answer(
                "❗ Минимальное количество участников — 10",
                reply_markup=back_inline_keyboard()
            )
            return
        if target > 10000:
            await message.answer(
                "❗ Максимальное количество участников — 10 000",
                reply_markup=back_inline_keyboard()
            )
            return
    except ValueError:
        await message.answer(
            "⚠️ Укажите корректное число (например: 100)",
            reply_markup=back_inline_keyboard()
        )
        return

    data = await state.get_data()
    invite_link = data.get("invite_link")
    chat_id = data.get("chat_id")

    if not invite_link or not chat_id:
        await message.answer(
            "❗ Внутренняя ошибка: данные канала утеряны. Начните заново.",
            reply_markup=back_inline_keyboard()
        )
        await state.clear()
        return

    # Calculate cost and validate balance
    cost = target * PER_PERSON_COST
    if user.balance < cost:
        missing = cost - user.balance
        await message.answer(
            f"❌ Недостаточно алмазов!\n"
            f"Требуется: {cost} 💎\n"
            f"Ваш баланс: {user.balance} 💎\n"
            f"Не хватает: {missing} 💎",
            reply_markup=back_inline_keyboard()
        )
        await state.clear()
        return

    # Create task with atomic transaction
    try:
        # Use database transaction for atomic operations
        with db.atomic():  # Assuming `db` is your Peewee database instance
            # Deduct balance
            user.balance -= cost
            user.save()
            
            # Create task
            task = Task.create(
                invite_link=invite_link,
                chat_id=chat_id,
                reward=LOCAL_TASK_REWARD,
                is_active=True,
                owner_id=message.from_user.id,
                target_subscribers=target,
                current_subscribers=0
            )

        # Log to admin chat if configured
        if TASK_LOG_CHAT_ID:
            try:
                await bot.send_message(
                    TASK_LOG_CHAT_ID,
                    f"💎 Новое задание #{task.id}\n"
                    f"Владелец: {message.from_user.id}\n"
                    f"Канал: {invite_link}\n"
                    f"Цель: {target} участников\n"
                    f"Стоимость: {cost} 💎"
                )
            except Exception as e:
                logger.error(f"Failed to log task creation: {e}")

        await message.answer(
            f"✅ Задание успешно создано!\n"
            f"🎯 Цель: {target} участников\n"
            f"💎 Списано: {cost} алмазов\n"
            f"💰 Текущий баланс: {user.balance} 💎\n\n"
            f"Бот начнёт привлекать участников в течение 15 минут.",
            reply_markup=None  # Clean interface after completion
        )
        
    except Exception as e:
        # Refund on failure
        try:
            user.balance += cost
            user.save()
        except Exception as refund_error:
            logger.critical(f"Refund failed after task creation error: {refund_error}")
        
        await message.answer(
            "⚠️ Ошибка при создании задания. Средства возвращены на баланс.\n"
            "Попробуйте позже или обратитесь в поддержку.",
            reply_markup=back_inline_keyboard()
        )
        logger.error(f"Task creation failed for user {message.from_user.id}: {e}")
    finally:
        await state.clear()