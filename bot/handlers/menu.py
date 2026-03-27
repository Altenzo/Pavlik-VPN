from aiogram import Router, F, types
from bot.keyboards.main_menu import get_main_menu_keyboard
from bot.keyboards.subscriptions import get_subscriptions_keyboard

from bot.keyboards.common import get_back_keyboard

menu_router = Router()

@menu_router.callback_query(F.data == "profile")
async def show_profile(callback: types.CallbackQuery):
    """
    Показ профиля пользователя
    """
    await callback.message.edit_text(
        f"👤 **Мой профиль**\n\n"
        f"🆔 Ваш ID: `{callback.from_user.id}`\n"
        f"📅 Статус подписки: **Не активна** ❌\n\n"
        "Купите подписку или активируйте тест, чтобы начать!",
        reply_markup=get_back_keyboard(),
        parse_mode="Markdown"
    )
    await callback.answer()

@menu_router.callback_query(F.data == "instructions")
async def show_instructions(callback: types.CallbackQuery):
    """
    Инструкция по подключению
    """
    await callback.message.edit_text(
        "📖 **Как подключить VPN?**\n\n"
        "1️⃣ Скачайте приложение **v2rayNG** (Android) или **FoXray** (iOS).\n"
        "2️⃣ Скопируйте ссылку, которую выдаст бот (она начинается на `vless://`).\n"
        "3️⃣ Нажмите кнопку '+' в приложении и выберите 'Импорт из буфера обмена'.\n"
        "4️⃣ Нажмите кнопку подключения и наслаждайтесь свободным интернетом! 🌍",
        reply_markup=get_back_keyboard(),
        parse_mode="Markdown"
    )
    await callback.answer()

@menu_router.callback_query(F.data == "buy_subscription")
async def select_subscription(callback: types.CallbackQuery):
    """
    Выбор тарифа
    """
    await callback.message.edit_text(
        "💎 **Выберите подходящий тариф:**\n\n"
        "Все тарифы включают безлимитный трафик на максимальной скорости. 🚀",
        reply_markup=get_subscriptions_keyboard(),
        parse_mode="Markdown"
    )
    await callback.answer()

@menu_router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery):
    """
    Возврат в главное меню
    """
    await callback.message.edit_text(
        f"Привет, {callback.from_user.first_name}! 🚀\n\n"
        "Добро пожаловать в **Павлик VPN**. Я помогу тебе получить быстрый и безопасный доступ "
        "в интернет из любой точки мира. 🌍\n\n"
        "Выбери нужное действие ниже: 👇",
        reply_markup=get_main_menu_keyboard(),
        parse_mode="Markdown"
    )
    await callback.answer()
