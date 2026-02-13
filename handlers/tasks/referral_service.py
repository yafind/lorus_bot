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

    bonus = int(round(task_reward * 0.1))
    referrer.balance += bonus
    referrer.referrals_count += 1
    referrer.save()