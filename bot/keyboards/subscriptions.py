from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def get_subscriptions_keyboard() -> InlineKeyboardMarkup:
    """
    Выбор тарифа
    """
    builder = InlineKeyboardBuilder()
    
    builder.row(InlineKeyboardButton(text="1 месяц — 149 ₽ / 1.9 USD", callback_data="select_sub:month_1:149"))
    builder.row(InlineKeyboardButton(text="3 месяца — 449 ₽ / 5.7 USD", callback_data="select_sub:month_3:449"))
    builder.row(InlineKeyboardButton(text="6 месяцев — 899 ₽ / 11.4 USD", callback_data="select_sub:month_6:899"))
    builder.row(InlineKeyboardButton(text="12 месяцев — 1499 ₽ / 19.1 USD", callback_data="select_sub:month_12:1499"))
    
    # Кнопка назад
    builder.row(InlineKeyboardButton(
        text="Назад", 
        callback_data="back_to_main", 
        icon_custom_emoji_id="5258236805890710909"
    ))
    
    return builder.as_markup()

def get_payment_methods_keyboard(tariff_key: str, amount: float) -> InlineKeyboardMarkup:
    """
    Выбор способа оплаты
    """
    builder = InlineKeyboardBuilder()
    
    # СБП
    builder.row(InlineKeyboardButton(
        text="СБП", 
        callback_data=f"buy:{tariff_key}:{amount}:sbp",
        icon_custom_emoji_id="5472095442445542168"
    ))
    
    # Крипта
    builder.row(InlineKeyboardButton(
        text="Криптовалюта", 
        callback_data=f"buy:{tariff_key}:{amount}:crypto",
        icon_custom_emoji_id="5472191413489771345"
    ))
    
    # Кнопка назад
    builder.row(InlineKeyboardButton(
        text="Назад к тарифам", 
        callback_data="buy_subscription",
        icon_custom_emoji_id="5258236805890710909"
    ))
    
    return builder.as_markup()
