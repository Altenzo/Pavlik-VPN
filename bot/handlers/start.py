from aiogram import Router, types
from aiogram.filters import CommandStart

from sqlalchemy.ext.asyncio import AsyncSession
from apps.db.repositories.user import get_user_by_id, register_user
from bot.keyboards.main_menu import get_main_menu_keyboard

# Создаем роутер для этого модуля
start_router = Router()

@start_router.message(CommandStart())
async def cmd_start(message: types.Message, session: AsyncSession):
    """
    Хендлер на команду /start с регистрацией в БД
    """
    # Проверяем, есть ли юзер в базе
    user = await get_user_by_id(session, message.from_user.id)
    
    if not user:
        # Если нет — регистрируем
        await register_user(
            session, 
            message.from_user.id, 
            message.from_user.username, 
            message.from_user.full_name
        )
        print(f"Зарегистрирован новый юзер: {message.from_user.full_name}")

    await message.answer(
        f"Привет, {message.from_user.first_name}! 🚀\n\n"
        "Добро пожаловать в **Павлик VPN**. Я помогу тебе получить быстрый и безопасный доступ "
        "в интернет из любой точки мира. 🌍\n\n"
        "Выбери нужное действие ниже: 👇",
        reply_markup=get_main_menu_keyboard(),
        parse_mode="Markdown"
    )
