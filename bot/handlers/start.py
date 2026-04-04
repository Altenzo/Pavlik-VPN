from aiogram import Router, types
from aiogram.filters import CommandStart, CommandObject
from sqlalchemy.ext.asyncio import AsyncSession
from apps.db.repositories.user import get_user_by_id, register_user
from bot.keyboards.main_menu import get_main_menu_keyboard

start_router = Router()

@start_router.message(CommandStart())
async def cmd_start(message: types.Message, command: CommandObject, session: AsyncSession):
    user_id = message.from_user.id
    user = await get_user_by_id(session, user_id)

    if not user:
        args = command.args  # правильный способ получить аргумент после /start
        referred_by = None

        if args and args.isdigit():
            referred_by_id = int(args)
            if referred_by_id != user_id:
                referrer = await get_user_by_id(session, referred_by_id)
                if referrer:
                    referred_by = referred_by_id

        user = await register_user(
            session,
            user_id,
            message.from_user.username,
            message.from_user.full_name,
            referred_by=referred_by
        )

    await message.answer(
        f"<tg-emoji emoji-id=\"5258152182150077732\">⚡</tg-emoji> <b>Blago VPN — Ваш персональный ключ к свободе.</b>\n\n"
        f"Забудьте о границах в интернете. Мы обеспечиваем сверхбыстрое соединение, абсолютную анонимность и доступ к любому контенту в один клик.\n\n"
        f"<tg-emoji emoji-id=\"5260221883940347555\">🚀</tg-emoji> <b>Наши преимущества:</b>\n"
        f"  •  <b>Скорость:</b> До 1 Гбит/с без задержек.\n"
        f"  •  <b>Приватность:</b> Мы уважаем твое право на частную жизнь и не храним историю твоих действий.\n"
        f"  •  <b>Простота:</b> Настройка за 30 секунд прямо в Telegram.\n\n"
        f"<i>Ваша безопасность — наша работа. Подключайтесь и летайте!</i>",
        reply_markup=get_main_menu_keyboard(user),
        parse_mode="HTML"
    )
