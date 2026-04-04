from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def get_trial_confirmation_keyboard() -> InlineKeyboardMarkup:
    """
    Клавиатура подтверждения активации пробного периода (убираем стандартные смайлики)
    """
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(
            text="Подтверждаю активацию", 
            callback_data="claim_trial", 
            icon_custom_emoji_id="5260726538302660868",
            style="success"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="Отмена", 
            callback_data="back_to_main", 
            icon_custom_emoji_id="5260342697075416641", 
            style="danger"
        )
    )
    
    return builder.as_markup()
