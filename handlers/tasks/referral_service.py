import logging
from database.models import User
from loader import bot

async def process_referral_reward(user: User, task_reward: float):
    if user.is_active_referral or user.task_count < 3 or not user.referral:
        return

    user.is_active_referral = True
    user.save()

    ref_id = user.referral  # Already an integer
    referrer = User.get_or_none(User.user_id == ref_id)
    if not referrer:
        return

    # Бонус 10% от награды за задание
    bonus = int(round(task_reward * 0.1))
    # Дополнительно 3 алмаза за активацию реферала
    activation_bonus = 3
    
    referrer.balance += bonus + activation_bonus
    referrer.referrals_count += 1
    referrer.save()
    
    # Уведомление рефереру об активации
    try:
        username = user.username if user.username else f"ID{user.user_id}"
        await bot.send_message(
            ref_id,
            f"🎉 <b>Ваш реферал стал активным!</b>\n\n"
            f"👤 Реферал: @{username}\n"
            f"💎 Награда за активацию: +{activation_bonus} алмазов\n"
            f"💰 Бонус от задания: +{bonus} алмазов\n\n"
            f"Теперь вы будете получать 10% от всех его наград!",
            parse_mode="HTML"
        )
    except Exception as e:
        logging.warning(f"Failed to notify referrer {ref_id}: {e}")