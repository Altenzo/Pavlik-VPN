from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_referral_keyboard(ref_link: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Скопировать реферальную ссылку",
            callback_data="copy_ref_link",
            icon_custom_emoji_id="5260687681733533075",
            style="primary"
        )],
        [InlineKeyboardButton(
            text="Вернуться в меню",
            callback_data="back_to_main",
            icon_custom_emoji_id="5258236805890710909"
        , style="danger")]
    ])
