import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from peewee import (
    PostgresqlDatabase,
    Model,
    IntegerField,
    CharField,
    BigIntegerField,
    BooleanField,
    DateTimeField,
    AutoField,
    Check,
    fn
)

# Загрузка переменных окружения
load_dotenv()

# Валидация критически важных переменных окружения
required_env_vars = ['DB_NAME', 'DB_USER', 'DB_PASSWORD', 'DB_HOST', 'DB_PORT']
missing_vars = [var for var in required_env_vars if not os.getenv(var)]
if missing_vars:
    raise EnvironmentError(
        f"Отсутствуют обязательные переменные окружения: {', '.join(missing_vars)}\n"
        "Проверьте файл .env"
    )

# Инициализация подключения к БД
db = PostgresqlDatabase(
    os.getenv('DB_NAME', 'stars_bot'),
    user=os.getenv('DB_USER', 'stars_user'),
    password=os.getenv('DB_PASSWORD'),  # Теперь точно существует
    host=os.getenv('DB_HOST', 'localhost'),
    port=int(os.getenv('DB_PORT', 5432)),
    autorollback=True,
    autoconnect=True
)


class User(Model):
    """
    Модель пользователя Telegram.
    ВАЖНО: table_name = 'users' — избегаем зарезервированного слова 'user' в PostgreSQL
    """
    user_id = BigIntegerField(primary_key=True, unique=True, index=True)
    username = CharField(null=True, index=True)
    balance = BigIntegerField(default=0)  # Алмазы хранятся как целые числа (НЕ float!)
    date = DateTimeField(default=lambda: datetime.now(timezone.utc))  # UTC время регистрации
    referral = BigIntegerField(null=True, index=True)  # user_id реферера
    boost = BooleanField(default=False)
    last_farm_time = DateTimeField(null=True)
    last_active = DateTimeField(default=lambda: datetime.now(timezone.utc))  # UTC
    task_count = IntegerField(default=0)
    task_count_diamonds = IntegerField(default=0)
    can_exchange = BooleanField(default=False)
    referrals_count = IntegerField(default=0, index=True)
    is_active_referral = BooleanField(default=False, index=True)

    class Meta:
        database = db
        table_name = 'users'  # КРИТИЧЕСКИ ВАЖНО: избегаем зарезервированного слова 'user'


class Root(Model):
    """Модель для хранения root-пользователей (администраторов)"""
    root_id = BigIntegerField(primary_key=True, unique=True, index=True)

    class Meta:
        database = db
        table_name = 'roots'


class Task(Model):
    """
    Задания на подписку на каналы.
    owner_id хранится как BigIntegerField (не ForeignKey) для отказоустойчивости:
    - Пользователь может удалить аккаунт, но задание должно остаться
    - Упрощает миграции и отладку
    """
    id = AutoField()
    invite_link = CharField()
    chat_id = BigIntegerField(index=True)  # ID канала в Telegram (часто отрицательный)
    reward = IntegerField(default=2)
    is_active = BooleanField(default=True, index=True)
    created_at = DateTimeField(default=lambda: datetime.now(timezone.utc))
    owner_id = BigIntegerField(null=True, index=True)  # user_id создателя задания
    target_subscribers = IntegerField(default=1)
    current_subscribers = IntegerField(default=0)

    class Meta:
        database = db
        table_name = 'tasks'


class UserSubscriptions(Model):
    """
    Фиксация подписок пользователей на каналы.
    ВАЖНО: channel_id — BigIntegerField, так как ID каналов в Telegram это целые числа
    """
    user_id = BigIntegerField(index=True)
    channel_id = BigIntegerField(index=True)  # Не CharField! ID канала — число
    timestamp = DateTimeField(default=lambda: datetime.now(timezone.utc))

    class Meta:
        database = db
        table_name = 'user_subscriptions'
        indexes = (
            (('user_id', 'channel_id'), True),  # Уникальная пара: пользователь + канал
        )


class Gift(Model):
    """Подарки для обмена алмазов"""
    id = AutoField()
    internal_name = CharField(unique=True, max_length=64, index=True)
    display_name = CharField(max_length=255)
    diamond_cost = IntegerField(index=True)
    is_active = BooleanField(default=True, index=True)
    is_virtual = BooleanField(default=False)

    class Meta:
        database = db
        table_name = 'gifts'


class PendingReward(Model):
    """
    Отложенные награды (начисление алмазов через 3 дня после выполнения задания).
    ВАЖНО: все награды хранятся как целые числа (IntegerField), НЕ float!
    """
    user_id = BigIntegerField(index=True)  # user_id получателя
    task_key = CharField(index=True)  # Уникальный ключ задания (например: 'subgram:123')
    task_title = CharField(null=True)
    diamonds = IntegerField()  # Целое число алмазов
    status = CharField(
        default="pending",
        constraints=[Check("status IN ('pending', 'completed', 'failed')")]
    )
    completed_at = DateTimeField(default=lambda: datetime.now(timezone.utc))  # Время успешной проверки
    scheduled_at = DateTimeField(index=True)  # Время запланированного начисления (completed_at + 3 дня)
    created_at = DateTimeField(default=lambda: datetime.now(timezone.utc))

    class Meta:
        database = db
        table_name = 'pending_rewards'
        indexes = (
            (('user_id', 'task_key'), True),  # Уникальность: пользователь не может выполнить одно задание дважды
            (('status', 'scheduled_at'), False),  # Оптимизация для фонового воркера
            (('user_id', 'status'), False),  # Частые запросы: "показать все pending награды пользователя"
        )


def create_tables_safe():
    """
    Создаёт таблицы в базе данных, если они ещё не существуют.
    Автоматически подключается к БД при необходимости.
    """
    if db.is_closed():
        db.connect()
    try:
        db.create_tables([
            User,
            Root,
            Task,
            UserSubscriptions,
            Gift,
            PendingReward,
        ], safe=True)
        print("✓ Таблицы успешно созданы или уже существуют")
    except Exception as e:
        print(f"✗ Ошибка при создании таблиц: {e}")
        raise
    finally:
        if not db.is_closed():
            db.close()


def initialize_database():
    """
    Полная инициализация БД: подключение + создание таблиц.
    Вызывайте эту функцию при старте бота.
    """
    try:
        create_tables_safe()
        print(f"✓ База данных инициализирована: {os.getenv('DB_NAME')}")
    except Exception as e:
        print(f"✗ Критическая ошибка инициализации БД: {e}")
        raise


initialize_database()