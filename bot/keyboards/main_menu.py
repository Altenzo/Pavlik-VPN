from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from apps.db.models.user import User

def get_main_menu_keyboard(user: User) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    # Ряд 0: Купить
    builder.row(
        InlineKeyboardButton(
            text="Купить VPN",
            callback_data="buy_subscription",
            icon_custom_emoji_id="5258152182150077732",
            style="primary"
        )
    )

    # Ряд 1: Пробный период (если не использован)
    if not user.trial_used:
        builder.row(
            InlineKeyboardButton(
                text="Бесплатный пробный период на 3 дня",
                callback_data="confirm_trial_request",
                icon_custom_emoji_id="5258185631355378853",
                style="success"
            )
        )

    # Ряд 2: Мой профиль и Рефералы
    builder.row(
        InlineKeyboardButton(
            text="Мой профиль",
            callback_data="profile",
            icon_custom_emoji_id="5258011929993026890"
        ),
        InlineKeyboardButton(
            text="Рефералы",
            callback_data="referrals",
            icon_custom_emoji_id="5258362837411045098"
        )
    )

    # Ряд 3: Инструкция
    builder.row(
        InlineKeyboardButton(
            text="Инструкция по подключению",
            callback_data="instructions",
            icon_custom_emoji_id="5258328383183396223",
            style="primary"
        )
    )

    # Ряд 4: Сменить язык
    builder.row(
        InlineKeyboardButton(
            text="🌐 Сменить язык / Change language",
            callback_data="select_lang"
        )
    )

    # Ряд 5: Поддержка → blago_vpn_manager | Канал → blago_vpn_news
    builder.row(
        InlineKeyboardButton(
            text="Поддержка",
            url="https://t.me/blago_vpn_manager",
            icon_custom_emoji_id="5258179403652801593"
        ),
        InlineKeyboardButton(
            text="Наш канал",
            url="https://t.me/blago_vpn_news",
            icon_custom_emoji_id="5260268501515377807"
        )
    )

    return builder.as_markup()
