from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from config import config


class BanMiddleware(BaseMiddleware):
    """
    Блокирует взаимодействие забаненных пользователей с ботом.
    Администраторы проверке не подлежат.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        # Администраторы не блокируются
        if data.get("is_admin"):
            return await handler(event, data)

        user = data.get("event_from_user")
        session = data.get("session")

        if user and session:
            from apps.db.models.user import User
            db_user = await session.get(User, user.id)
            if db_user and db_user.is_banned:
                reason = db_user.ban_reason or "Нарушение правил"
                ban_msg = (
                    f"🚫 <b>Ваш аккаунт заблокирован</b>\n\n"
                    f"Причина: {reason}\n\n"
                    f"Для обжалования обратитесь в поддержку: {config.SUPPORT_USERNAME}"
                )
                if isinstance(event, Update):
                    if event.callback_query:
                        try:
                            await event.callback_query.answer(
                                f"🚫 Вы заблокированы. Причина: {reason}", show_alert=True
                            )
                        except Exception:
                            pass
                    elif event.message:
                        try:
                            await event.message.answer(ban_msg, parse_mode="HTML")
                        except Exception:
                            pass
                return

        return await handler(event, data)
