from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """
    Создает главное меню бота
    """
    builder = InlineKeyboardBuilder()
    
    # Ряд 1
    builder.row(
        InlineKeyboardButton(text="💎 Купить подписку", callback_data="buy_subscription"),
        InlineKeyboardButton(text="👤 Мой профиль", callback_data="profile")
    )
    
    # Ряд 2
    builder.row(
        InlineKeyboardButton(text="📖 Как подключить?", callback_data="instructions"),
        InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")
    )
    
    # Ряд 3: Теперь это URL кнопка
    builder.row(
        InlineKeyboardButton(text="🎁 Попробовать бесплатно", url="https://youtube.com")
    )
    
    return builder.as_markup()
