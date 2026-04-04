from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message
from config import config


class AdminMiddleware(BaseMiddleware):
    """
    Добавляет is_admin в data для каждого апдейта.
    Хендлеры могут проверять data['is_admin'] вместо config.ADMIN_IDS напрямую.
    """
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        data["is_admin"] = bool(user and user.id in config.ADMIN_IDS)
        return await handler(event, data)
