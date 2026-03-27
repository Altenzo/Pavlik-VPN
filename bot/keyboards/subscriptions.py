from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def get_subscriptions_keyboard() -> InlineKeyboardMarkup:
    """
    Клавиатура выбора тарифа
    """
    builder = InlineKeyboardBuilder()
    
    builder.row(InlineKeyboardButton(text="⏳ 1 День — 50₽", callback_data="buy_day"))
    builder.row(InlineKeyboardButton(text="🗓 1 Месяц — 300₽", callback_data="buy_month"))
    builder.row(InlineKeyboardButton(text="👑 1 Год — 3000₽", callback_data="buy_year"))
    
    # Кнопка назад
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main"))
    
    return builder.as_markup()
