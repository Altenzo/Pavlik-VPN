from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def get_payment_keyboard(pay_url: str, transaction_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    # Кнопка оплаты
    builder.row(InlineKeyboardButton(
        text="Оплатить",
        url=pay_url,
        icon_custom_emoji_id="5445353829304387411",
        style="success"
    ))

    # Кнопка назад (кнопку "Я оплатил" убрали — работает автоподтверждение)
    builder.row(InlineKeyboardButton(
        text="Назад к тарифам",
        callback_data="buy_subscription",
        icon_custom_emoji_id="5258236805890710909",
        style="danger"
    ))

    return builder.as_markup()
