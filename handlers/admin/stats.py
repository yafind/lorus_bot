"""Admin statistics handlers."""
import logging
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.types import CallbackQuery
from database.models import User
from .core import is_admin, safe_edit_or_answer, format_number, back_kb
import aiohttp
from typing import Dict, Any

logger = logging.getLogger(__name__)
router = Router()


def get_user_stats() -> int:
    """Get total users count."""
    return User.select().count()


def get_boosted_users_count() -> int:
    """Get users with boost."""
    return User.select().where(User.boost == True).count()


async def get_subgram_statistics(api_key: str) -> Dict[str, Any]:
    """Fetch statistics from Subgram API."""
    url = "https://api.subgram.org/get-statistic/"  # FIXED: Removed trailing spaces
    headers = {"Auth": api_key}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers) as response:
                data = await response.json()
                if data.get("status") == "ok" and data.get("code") == 200:
                    stats = data["data"]
                    today = datetime.today().date()
                    week_start = today - timedelta(days=today.weekday())  # Monday as week start
                    month_start = today.replace(day=1)

                    total_today = total_week = total_month = 0.0
                    for stat in stats:
                        stat_date = datetime.strptime(stat["date"], "%Y-%m-%d").date()
                        amount = stat["amount"]
                        if stat_date == today:
                            total_today += amount
                        if stat_date >= week_start:
                            total_week += amount
                        if stat_date >= month_start:
                            total_month += amount
                    return {
                        "total_today": total_today,
                        "total_week": total_week,
                        "total_month": total_month
                    }
                else:
                    return {"error": True, "message": data.get("message", "Unknown error")}
    except Exception as e:
        logger.exception("Subgram API error")
        return {"error": True, "message": str(e)}


@router.callback_query(F.data == "admin")
async def admin_handler(call: CallbackQuery):
    """Show admin panel."""
    if not is_admin(call.from_user.id):
        await call.answer("🚫 Доступ запрещён.", show_alert=True)
        return
    
    user_count = get_user_stats()
    boosted_users = get_boosted_users_count()
    new_users_today = User.select().where(User.date >= datetime.now().date()).count()

    msg = (
        f"📊 *Статистика*\n\n"
        f"👥 Пользователей: {format_number(user_count)}\n"
        f"🆕 Новых сегодня: {format_number(new_users_today)}\n"
        f"🚀 С бустом: {format_number(boosted_users)}"
    )
    
    from .keyboards import admin_keyboard
    try:
        await call.message.delete()
        await call.message.answer(msg, parse_mode="MarkdownV2", reply_markup=admin_keyboard())  # FIXED: Use MarkdownV2 for safety
    except Exception as e:
        logger.debug(f"Delete failed, trying edit: {e}")
        try:
            await call.message.edit_text(msg, reply_markup=admin_keyboard(), parse_mode="MarkdownV2")  # FIXED: Use MarkdownV2
        except Exception as e:
            logger.exception(f"Failed to edit message: {e}")
    
    await call.answer()


@router.callback_query(F.data == "admin_stats")
async def show_referral_stats(call: CallbackQuery):
    """Show top referrers."""
    if not is_admin(call.from_user.id):
        await call.answer("🚫 Доступ запрещён.", show_alert=True)
        return

    top_users = (
        User
        .select()
        .where(User.referrals_count > 0)
        .order_by(User.referrals_count.desc())
        .limit(10)
    )

    if not top_users:
        await safe_edit_or_answer(call, "📭 Нет пользователей с рефералами.", reply_markup=back_kb())
        return

    lines = []
    for i, user in enumerate(top_users, 1):
        # FIXED: Escape Markdown special characters in usernames
        name = f"@{user.username}" if user.username else f"ID{user.user_id}"
        name = name.replace("_", "\\_").replace("*", "\\*").replace("[", "\\[")
        lines.append(f"{i}\\. {name} — {user.referrals_count}")  # FIXED: Escape dot for MarkdownV2

    text = "🏆 *ТОП\\-10 по рефералам*\n\n" + "\n".join(lines)  # FIXED: Escape special chars for MarkdownV2
    await safe_edit_or_answer(call, text, reply_markup=back_kb(), parse_mode="MarkdownV2")


@router.callback_query(F.data == "stats")
async def show_referral_stats_old(call: CallbackQuery):
    """Show top referrers (legacy)."""
    await show_referral_stats(call)