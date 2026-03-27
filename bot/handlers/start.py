from aiogram import Router, types
from aiogram.filters import CommandStart

from bot.keyboards.main_menu import get_main_menu_keyboard

# Создаем роутер для этого модуля
start_router = Router()

@start_router.message(CommandStart())
async def cmd_start(message: types.Message):
    """
    Хендлер на команду /start
    """
    await message.answer(
        f"Привет, {message.from_user.first_name}! 🚀\n\n"
        "Добро пожаловать в **Павлик VPN**. Я помогу тебе получить быстрый и безопасный доступ "
        "в интернет из любой точки мира. 🌍\n\n"
        "Выбери нужное действие ниже: 👇",
        reply_markup=get_main_menu_keyboard(),
        parse_mode="Markdown"
    )
