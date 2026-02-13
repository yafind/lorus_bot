import os
from dotenv import load_dotenv

load_dotenv()

telegram_token = os.getenv('TELEGRAM_TOKEN')
subgram_api = os.getenv('SUBGRAM_API')
FLYER_KEY = os.getenv('FLYER_KEY')

chat_game = int(os.getenv('CHAT_GAME', 0))
payment_chat = os.getenv('PAYMENT_CHAT')
payment_chat_id = int(os.getenv('PAYMENT_CHAT_ID', 0))
FRAUD_CHAT_ID = int(os.getenv('FRAUD_CHAT_ID', 0))
TASK_LOG_CHAT_ID = int(os.getenv('TASK_LOG_CHAT_ID', 0))
