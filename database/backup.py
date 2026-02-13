import os
import sys
import subprocess
from datetime import datetime

# Добавляем корень проекта в PATH
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BACKUP_DIR = os.path.join(os.path.dirname(__file__), "backups")
os.makedirs(BACKUP_DIR, exist_ok=True)

def backup_database():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    dump_file = os.path.join(BACKUP_DIR, f"stars_bot_{timestamp}.dump")

    env = os.environ.copy()

    try:
        result = subprocess.run([
            "pg_dump",
            "-U", "stars_user",
            "-h", "localhost",
            "-p", "5432",
            "-F", "c",
            "stars_bot",
            "-f", dump_file
        ], env=env, check=True, capture_output=True, text=True)
        print(f"✅ Бэкап сохранён: {dump_file}")

        # Удаляем бэкапы старше 7 дней
        retention_days = 7
        cutoff = datetime.now().timestamp() - retention_days * 86400
        for fname in os.listdir(BACKUP_DIR):
            path = os.path.join(BACKUP_DIR, fname)
            if os.path.getmtime(path) < cutoff:
                os.remove(path)
                print(f"🗑️ Удалён старый бэкап: {fname}")

    except subprocess.CalledProcessError as e:
        print(f"❌ Ошибка бэкапа: {e.stderr}")
        sys.exit(1)

if __name__ == "__main__":
    backup_database()