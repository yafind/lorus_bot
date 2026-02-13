# loader.py
from aiogram import Dispatcher, Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
import redis.asyncio as redis
from config import telegram_token

redis_client = redis.Redis(
    host='localhost',
    port=6379,
    db=1,
    decode_responses=False
)

storage = RedisStorage(redis=redis_client)

bot = Bot(
    token=telegram_token,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher(storage=storage)