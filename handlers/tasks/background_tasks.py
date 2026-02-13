"""Background tasks for reward processing."""
import logging
import asyncio
from datetime import datetime

from database.models import PendingReward, User
from handlers.tasks.referral_service import process_referral_reward
from loader import bot

logger = logging.getLogger(__name__)


async def award_user(user: "User", reward: int) -> bool:
    """Начислить награду пользователю и обработать реферальную систему."""
    try:
        # Атомарное обновление БД
        User.update({
            User.balance: User.balance + int(reward),
            User.task_count: User.task_count + 1,
            User.task_count_diamonds: User.task_count_diamonds + int(reward)
        }).where(User.user_id == user.user_id).execute()
        
        user = User.get_by_id(user.user_id)
        await process_referral_reward(user, int(reward))
        return True
    except Exception as e:
        logger.exception(f"Ошибка при начислении награды {user.user_id}: {e}")
        return False


async def process_pending_rewards():
    """Unified pending rewards processor (runs every 5 minutes)."""
    while True:
        try:
            now = datetime.now()
            pending = list(
                PendingReward.select().where(
                    (PendingReward.status == "pending") &
                    (PendingReward.scheduled_at <= now)
                )
            )

            for pr in pending:
                try:
                    user = User.get_or_none(User.user_id == pr.user_id)
                    if not user:
                        pr.status = "completed"
                        pr.save()
                        continue

                    if await award_user(user, pr.diamonds):
                        pr.status = "completed"
                        pr.save()

                        title = pr.task_title or "задание"
                        try:
                            await bot.send_message(
                                pr.user_id,
                                f"💎 +{int(pr.diamonds)} алмазов за {title}"
                            )
                        except Exception:
                            pass
                except Exception as e:
                    logger.exception(f"Ошибка награды {pr.id}: {e}")

        except Exception as e:
            logger.exception(f"Ошибка обработки отложенных наград: {e}")

        await asyncio.sleep(300)
