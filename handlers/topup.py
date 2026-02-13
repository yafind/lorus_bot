# handlers/topup.py
from aiogram import Router, F
from aiogram.types import CallbackQuery
from keyboards.keyboard import topup_keyboard

router = Router()

@router.callback_query(F.data == "topup_diamonds")
async def topup_diamonds_handler(call: CallbackQuery):
    text = (
        "💎 <b>Пополнить алмазы</b>\n\n"
        "Скоро будет доступна оплата через:\n"
        "• Telegram Stars ⭐\n"
        "• Криптовалюту\n"
        "• Банковские карты\n\n"
        "Сейчас можно пополнить только через поддержку:\n"
        "@supStarsbot"
    )
    
    await call.message.delete()
    
    await call.message.answer(
        text,
        parse_mode="HTML",
        reply_markup=topup_keyboard()
    )
    await call.answer()