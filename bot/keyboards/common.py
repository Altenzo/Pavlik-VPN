from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_back_keyboard() -> InlineKeyboardMarkup:
    """
    Возвращает одну кнопку 'Назад'
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")]
    ])
