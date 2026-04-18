from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import config

def get_subscriptions_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    builder.row(InlineKeyboardButton(text="1 месяц — 149 ₽", callback_data="select_sub:month_1:149"))
    builder.row(InlineKeyboardButton(text="3 месяца — 449 ₽", callback_data="select_sub:month_3:449"))
    builder.row(InlineKeyboardButton(text="6 месяцев — 899 ₽", callback_data="select_sub:month_6:899"))
    builder.row(InlineKeyboardButton(text="12 месяцев — 1499 ₽", callback_data="select_sub:month_12:1499"))

    builder.row(InlineKeyboardButton(
        text="Назад",
        callback_data="back_to_main",
        icon_custom_emoji_id="5258236805890710909"
    , style="danger"))

    return builder.as_markup()


def get_payment_methods_keyboard(tariff_key: str, amount: float) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    # СБП
    builder.row(InlineKeyboardButton(
        text="СБП",
        callback_data=f"buy:{tariff_key}:{int(float(amount))}:sbp",
        icon_custom_emoji_id="5472095442445542168"
    ))

    # Крипта — показываем только если Heleket настроен
    if config.HELEKET_MERCHANT_ID and config.HELEKET_API_KEY:
        builder.row(InlineKeyboardButton(
            text="Криптовалюта",
            callback_data=f"buy:{tariff_key}:{int(float(amount))}:crypto",
            icon_custom_emoji_id="5472191413489771345"
        ))

    # Активировать промокод
    builder.row(InlineKeyboardButton(
        text="Активировать промокод",
        callback_data="promo_code",
        icon_custom_emoji_id="5359719332542718652"
    ))

    # Назад
    builder.row(InlineKeyboardButton(
        text="Назад к тарифам",
        callback_data="buy_subscription",
        icon_custom_emoji_id="5258236805890710909"
    , style="danger"))

    return builder.as_markup()
