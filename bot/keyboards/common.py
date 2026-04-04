from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_back_keyboard() -> InlineKeyboardMarkup:
    """
    Возвращает одну кнопку 'Назад'
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад", callback_data="back_to_main", icon_custom_emoji_id="5258236805890710909", style="danger")]
    ])

def get_back_to_profile_keyboard() -> InlineKeyboardMarkup:
    """
    Возвращает одну кнопку 'Назад' (в профиль)
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад", callback_data="profile", icon_custom_emoji_id="5258236805890710909", style="danger")]
    ])
