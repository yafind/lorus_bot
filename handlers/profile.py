from aiogram import F, Router
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from database.models import User
from keyboards.keyboard import toggle_ref_reward_keyboard
from aiogram.exceptions import TelegramBadRequest

router = Router()


async def get_referral_rewards_info(user_id: int) -> str:
    active_refs = (User
                   .select()
                   .where(
                       (User.referral == user_id) &
                       (User.is_active_referral == True)
                   )
                   .order_by(User.task_count_diamonds.desc())
                   .limit(10))
    
    total_active = User.select().where(
        (User.referral == user_id) &
        (User.is_active_referral == True)
    ).count()
    
    total_reward = 0
    rewards_info = []
    
    for ref in active_refs:
        reward = int(round(ref.task_count_diamonds * 0.1))
        total_reward += reward
        username = ref.username if ref.username else f"user{ref.user_id}"
        rewards_info.append(f"• @{username}: {reward} 💎")
    
    more_info = f"\n<i>+{total_active - 10} других рефералов</i>" if total_active > 10 else ""
    
    if not rewards_info:
        return "🚫 Активных рефералов пока нет"
    
    return (
        f"💰 <b>Детальная статистика наград</b>\n"
        f"════════════════════\n"
        f"💎 <b>Общий доход:</b> {total_reward} 💎\n"
        "────────────────────\n"
        f"👥 <b>Топ-10 рефералов:</b>\n"
        + "\n".join(rewards_info) +
        more_info +
        "\n════════════════════"
    )


def build_profile_text_simple(user_id: int, full_name: str, user, active_refs: int, inactive_refs: int) -> str:
    referrer_info = "Первобытный"
    if user.referral:
        ref_id = user.referral  # Already an integer
        referrer = User.get_or_none(User.user_id == ref_id)
        if referrer:
            referrer_info = f"@{referrer.username} (ID: {ref_id})" if referrer.username else f"ID: {ref_id}"
        else:
            referrer_info = "Удалённый аккаунт"

    balance = int(user.balance)
    tasks_done = user.task_count_diamonds
    ref_link = f"https://t.me/BotFreeStarts_bot?start={user_id}"
    exchange_status = "🟢 Разблокирован" if user.can_exchange else "🔒 Не разблокирован"

    return (
        "💎 <b>Ваш профиль</b> 💎\n"
        "════════════════════\n"
        f"👤 <b>Имя:</b> {full_name}\n"
        f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
        f"🔗 <b>Реферальная ссылка:</b>\n"
        f"<code>{ref_link}</code>\n"
        "────────────────────\n"
        f"📨 <b>Приглашён от:</b> {referrer_info}\n"
        "────────────────────\n"
        f"💰 <b>Баланс:</b> {balance} 💎\n"
        f"🤝 <b>Рефералов: (доход 10%)</b>\n"
        f"   • Активных: {active_refs}\n"
        f"   • В ожидании: {inactive_refs}\n"
        f"✅ <b>Выполнено заданий:</b> {tasks_done}\n"
        f"🔄 <b>Обмен подарками:</b> {exchange_status}\n"
        "════════════════════"
    )


def build_profile_text(call: CallbackQuery, user, active_refs: int, inactive_refs: int) -> str:
    return build_profile_text_simple(call.from_user.id, call.from_user.full_name, user, active_refs, inactive_refs)


@router.callback_query(F.data == 'profile')
async def profile_handler(call: CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    user = User.get_or_none(User.user_id == user_id)

    if not user:
        await call.answer("❌ Профиль не найден. Напишите /start", show_alert=True)
        return

    await state.update_data(show_ref_rewards=False)
    
    active_refs = User.select().where(
        (User.referral == user_id) &
        (User.is_active_referral == True)
    ).count()
    inactive_refs = User.select().where(
        (User.referral == user_id) &
        (User.is_active_referral == False)
    ).count()

    profile_text = build_profile_text(call, user, active_refs, inactive_refs)
    profile_text += "\n\n⬇️ Награда от рефералов ⬇️"
    
    # Безопасная отправка: удаляем старое и отправляем новое
    try:
        await call.message.delete()
    except TelegramBadRequest:
        # Невозможно удалить сообщение для всех (например, истёк срок или нет прав) — игнорируем
        pass
    await call.message.answer(
        profile_text,
        parse_mode="HTML",
        reply_markup=toggle_ref_reward_keyboard(is_showing=False)
    )
    await call.answer()


@router.callback_query(F.data == 'toggle_ref_rewards')
async def toggle_ref_rewards_handler(call: CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    data = await state.get_data()
    show_ref_rewards = not data.get('show_ref_rewards', False)
    await state.update_data(show_ref_rewards=show_ref_rewards)
    
    user = User.get_or_none(User.user_id == user_id)
    if not user:
        await call.answer("❌ Профиль не найден. Напишите /start", show_alert=True)
        return

    active_refs = User.select().where(
        (User.referral == user_id) &
        (User.is_active_referral == True)
    ).count()
    inactive_refs = User.select().where(
        (User.referral == user_id) &
        (User.is_active_referral == False)
    ).count()

    profile_text = build_profile_text(call, user, active_refs, inactive_refs)
    
    if show_ref_rewards:
        ref_rewards_info = await get_referral_rewards_info(user_id)
        profile_text += f"\n\n{ref_rewards_info}"
    
    try:
        await call.message.delete()
    except TelegramBadRequest:
        pass
    await call.message.answer(
        profile_text,
        parse_mode="HTML",
        reply_markup=toggle_ref_reward_keyboard(is_showing=show_ref_rewards)
    )
    await call.answer()