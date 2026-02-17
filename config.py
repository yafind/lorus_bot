import os
from dotenv import load_dotenv

load_dotenv()

telegram_token = os.getenv('TELEGRAM_TOKEN')
subgram_api = os.getenv('SUBGRAM_API')
FLYER_KEY = os.getenv('FLYER_KEY')
MINI_APP_URL = os.getenv('MINI_APP_URL', '')
MINI_APP_HOST = os.getenv('MINI_APP_HOST', '127.0.0.1')
MINI_APP_PORT = int(os.getenv('MINI_APP_PORT', 8080))

chat_game = int(os.getenv('CHAT_GAME', 0))
payment_chat = os.getenv('PAYMENT_CHAT')
payment_chat_id = int(os.getenv('PAYMENT_CHAT_ID', 0))
FRAUD_CHAT_ID = int(os.getenv('FRAUD_CHAT_ID', 0))
TASK_LOG_CHAT_ID = int(os.getenv('TASK_LOG_CHAT_ID', 0))
