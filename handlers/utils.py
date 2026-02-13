"""Common utility functions for handlers."""
import logging
import re
from datetime import datetime
from database.models import User, Root

logger = logging.getLogger(__name__)


def is_admin(user_id: int) -> bool:
    """Check if user is admin."""
    return Root.get_or_none(Root.root_id == user_id) is not None


def get_task_completion_count(user_id: int) -> int:
    """Get number of completed tasks for user."""
    user = User.get_or_none(User.user_id == user_id)
    return user.task_count_diamonds if user else 0


def get_referral_count(user_id: int) -> int:
    """Get number of referrals for user."""
    return User.select().where(User.referral == user_id).count()


def create_user(user_id: int, referrer_id: int | None, tg_user) -> User:
    """Create new user with referral tracking and safety checks."""
    # Sanitize username for DB constraints and safety
    raw_username = tg_user.username or tg_user.first_name or f"user{user_id}"
    # Allow only safe characters; replace others with underscore
    username = re.sub(r'[^\w\-_.]', '_', raw_username[:32]).strip('_') or f"user{user_id}"

    # Create user record
    user = User.create(
        user_id=user_id,
        username=username,
        balance=0,
        date=datetime.now(),
        referral=referrer_id,
        boost=False,
        last_farm_time=None,
        last_active=datetime.now(),
        task_count=0,
        task_count_diamonds=0,
        can_exchange=False,
        referrals_count=0,
        is_active_referral=False
    )
    
    # Update referrer's count if valid referral
    if referrer_id:
        try:
            referrer = User.get_by_id(referrer_id)
            referrer.referrals_count += 1
            referrer.save()
            logger.info(f"Referral tracked: user {user_id} → referrer {referrer_id}")
        except User.DoesNotExist:
            logger.warning(f"Invalid referrer ID {referrer_id} for new user {user_id}")
    
    return user
