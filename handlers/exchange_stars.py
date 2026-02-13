from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database.models import User, Gift
from keyboards.keyboard import dynamic_gifts_keyboard, back_button_keyboard
from handlers.utils import is_admin, get_task_completion_count, get_referral_count
from loader import bot
from config import payment_chat as PAYMENT_CHAT_LINK, payment_chat_id as PAYMENT_CHAT_ID

router = Router()


@router.callback_query(F.data == "exchange_back")
async def back_to_gifts(call: CallbackQuery):
    await exchange_stars_menu(call)


@router.callback_query(F.data == "exchange_stars")
async def exchange_stars_menu(call: CallbackQuery):
    user = User.get_or_none(User.user_id == call.from_user.id)
    if not user:
        await call.answer("❌ Профиль не найден.", show_alert=True)
        return

    balance = int(user.balance)
    text = (
        f"✨ <b>Ваш баланс:</b> {balance} 💎\n\n"
        "‼️ <b>Условия обмена:</b>\n"
        "• ✅ Выполнить <b>10 заданий</b>\n"
        "• ✅ Пригласить <b>3 реферала</b>\n\n"
        "🔍 После первого обмена — условия больше не требуются!\n\n"
        "🎁 Выберите подарок для обмена:"
    )

    gifts = list(Gift.select().where(Gift.is_active == True))
    try:
        await call.message.delete()
        await call.message.answer(
            text,
            parse_mode="HTML",
            reply_markup=dynamic_gifts_keyboard(gifts)
        )
    except Exception:
        await call.message.edit_text(text, reply_markup=dynamic_gifts_keyboard(gifts), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data.startswith("gift:"))
async def handle_gift_selection(call: CallbackQuery):
    user_id = call.from_user.id
    user = User.get_or_none(User.user_id == user_id)
    if not user:
        await call.answer("❌ Пользователь не найден.", show_alert=True)
        return

    try:
        gift_id = int(call.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await call.answer("❗ Неверный формат подарка.", show_alert=True)
        return

    gift = Gift.get_or_none(Gift.id == gift_id, Gift.is_active == True)
    if not gift:
        await call.answer("🎁 Подарок недоступен.", show_alert=True)
        return

    # Проверка условий разблокировки
    if not user.can_exchange:
        tasks_done = get_task_completion_count(user_id)
        referrals = get_referral_count(user_id)

        if tasks_done < 10 or referrals < 3:
            errors = []
            if tasks_done < 10:
                errors.append(f"❌ Задания: {tasks_done}/10")
            if referrals < 3:
                errors.append(f"❌ Рефералы: {referrals}/3")
            await call.answer(
                f"🔻 Условия не выполнены!\n\n" + "\n".join(errors),
                show_alert=True
            )
            return
        user.can_exchange = True
        user.save()

    if user.balance < gift.diamond_cost:
        await call.answer(
            f"❌ Недостаточно алмазов! Нужно {gift.diamond_cost}, у вас {int(user.balance)}.",
            show_alert=True
        )
        return

    user.balance = int(user.balance) - int(gift.diamond_cost)
    user.save()

    success_text = (
        f"🎉 <b>Поздравляем!</b>\n\n"
        f"Вы выбрали подарок: <b>{gift.display_name}</b> за {gift.diamond_cost} 💎\n"
        f"✅ Запрос отправлен. Статус в <a href='{PAYMENT_CHAT_LINK}'>чате выплат</a>."
    )

    # Отправляем подтверждение
    try:
        await call.message.delete()
        await call.message.answer(
            success_text,
            parse_mode="HTML",
            reply_markup=back_button_keyboard()
        )
    except Exception:
        await call.message.answer(
            success_text,
            parse_mode="HTML",
            reply_markup=back_button_keyboard()
        )

    # Уведомление админов
    full_name = call.from_user.full_name or "—"
    username = call.from_user.username or "—"
    tasks_done = get_task_completion_count(user_id)
    referrals = get_referral_count(user_id)

    admin_text = (
        f"👤 <b>Пользователь:</b> <a href='tg://user?id={user_id}'>{full_name}</a> (@{username})\n"
        f"👥 Рефералов: {referrals} | Заданий: {tasks_done}\n"
        f"🎁 Подарок: {gift.display_name}\n"
        f"💰 Стоимость: {gift.diamond_cost} 💎\n"
        f"{'🟢 Обмен разблокирован' if user.can_exchange else '🟠 Обмен не разблокирован'}"
    )

    approve_btn = InlineKeyboardButton(
        text="✅ Одобрить",
        callback_data=f"approve_{user_id}_{gift.id}_{gift.diamond_cost}"
    )
    reject_btn = InlineKeyboardButton(
        text="❌ Отклонить",
        callback_data=f"reject_{user_id}_{gift.id}_{gift.diamond_cost}"
    )
    admin_kb = InlineKeyboardMarkup(inline_keyboard=[[approve_btn, reject_btn]])

    await bot.send_message(PAYMENT_CHAT_ID, admin_text, reply_markup=admin_kb, parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data.startswith("approve_"))
async def approve_exchange(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("❌ Доступ запрещён.", show_alert=True)
        return

    parts = call.data.split("_")
    if len(parts) < 4:
        await call.answer("⚠️ Ошибка данных.", show_alert=True)
        return

    try:
        user_id = int(parts[1])
        gift_id = int(parts[2])
        cost = int(parts[3])
    except (ValueError, IndexError):
        await call.answer("⚠️ Ошибка данных.", show_alert=True)
        return

    gift = Gift.get_or_none(Gift.id == gift_id)
    gift_name = gift.display_name if gift else "Подарок"

    updated_text = call.message.text
    if updated_text:
        updated_text = (
            updated_text
            .replace("в обработке", "выплачено")
            .replace("🟠", "🟢")
            .replace("🔴", "🟢")
        )
        await call.message.edit_text(updated_text, parse_mode="HTML")

    await bot.send_message(
        user_id,
        f"✅ Выплата за {cost} 💎 ({gift_name}) подтверждена!",
        reply_markup=back_button_keyboard()
    )


@router.callback_query(F.data.startswith("reject_"))
async def reject_exchange(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("❌ Доступ запрещён.", show_alert=True)
        return

    parts = call.data.split("_")
    if len(parts) < 4:
        await call.answer("⚠️ Ошибка данных.", show_alert=True)
        return

    try:
        user_id = int(parts[1])
        gift_id = int(parts[2])
        cost = int(parts[3])
    except (ValueError, IndexError):
        await call.answer("⚠️ Ошибка суммы.", show_alert=True)
        return

    user = User.get_or_none(User.user_id == user_id)
    if user:
        user.balance = int(user.balance) + int(cost)
        user.save()

    gift = Gift.get_or_none(Gift.id == gift_id)
    gift_name = gift.display_name if gift else "Подарок"

    updated_text = call.message.text
    if updated_text:
        updated_text = (
            updated_text
            .replace("в обработке", "отклонено")
            .replace("🟠", "🔴")
            .replace("🟢", "🔴")
        )
        await call.message.edit_text(updated_text, parse_mode="HTML")

    await bot.send_message(
        user_id,
        f"❌ Выплата за {cost} 💎 ({gift_name}) отклонена. Алмазы возвращены.",
        reply_markup=back_button_keyboard()
    )