import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.models import db, Root, Gift # type: ignore

YOUR_TELEGRAM_ID = 6085231879

def init_admin_and_gifts():
    db.connect()

    Root.get_or_create(root_id=YOUR_TELEGRAM_ID)
    print(f"✅ Админ {YOUR_TELEGRAM_ID} добавлен.")

    GIFTS = [
        ("teddy", "🧸", 33, True),
        ("heart", "💖", 33, True),
        ("rose", "🌹", 55, True),
        ("gift_box", "🎁", 55, True),
        ("champagne", "🍾", 83, True),
        ("rocket", "🚀", 83, True),
        ("bouquet", "💐", 83, True),
        ("cake", "🎂", 83, True),
        ("trophy", "🏆", 138, True),
        ("ring", "💍", 138, True),
        ("diamond_emoji", "💎", 138, True),
        ("premium_3m", "Telegram Premium на 3 месяца", 550, True),
        ("premium_6m", "Telegram Premium на 6 месяцев", 935, True),
        ("stars_100", "100 звёзд на аккаунт", 275, True),
        ("stars_500", "500 звёзд на аккаунт", 1265, True),
        ("stars_1000", "1000 звёзд на аккаунт", 2200, True),
    ]

    deleted = Gift.delete().execute()
    print(f"🗑️ Удалено {deleted} старых подарков.")

    for internal_name, display_name, cost, is_virtual in GIFTS:
        Gift.create(
            internal_name=internal_name,
            display_name=display_name,
            diamond_cost=cost,
            is_active=True,
            is_virtual=is_virtual
        )

    print(f"✅ Добавлено {len(GIFTS)} подарков.")
    db.close()

if __name__ == "__main__":
    init_admin_and_gifts()