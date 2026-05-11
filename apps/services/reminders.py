"""Фоновый сервис напоминаний о скором окончании подписки.

Логика:
- Пробный период (is_trial_subscription = True): одно напоминание за 1 день
  до окончания.
- Платная подписка: напоминания за 3 дня до окончания, каждые 12 часов.

Состояние хранится в `User.last_reminder_sent_at`. Поле сбрасывается в None
при активации триала, оплате и админской выдаче подписки — это гарантирует,
что после продления цикл напоминаний начнётся заново.
"""

import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select

from apps.db.database import async_session
from apps.db.models.user import User

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 30 * 60  # каждые 30 минут
PAID_REMINDER_WINDOW = timedelta(days=3)
PAID_REMINDER_COOLDOWN = timedelta(hours=12)
TRIAL_REMINDER_WINDOW = timedelta(days=1)


def _format_remaining(delta: timedelta) -> str:
    total_hours = int(delta.total_seconds() // 3600)
    days = total_hours // 24
    hours = total_hours % 24
    if days > 0 and hours > 0:
        return f"{days} д. {hours} ч."
    if days > 0:
        return f"{days} д."
    if hours > 0:
        return f"{hours} ч."
    minutes = max(1, int(delta.total_seconds() // 60))
    return f"{minutes} мин."


def _renew_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="Продлить",
            callback_data="buy_subscription",
            icon_custom_emoji_id="5258152182150077732",
            style="success",
        )
    )
    return builder.as_markup()


async def _send_trial_reminder(bot: Bot, user: User, remaining: timedelta) -> bool:
    text = (
        "<tg-emoji emoji-id=\"5258258882022612173\">⏰</tg-emoji> <b>Пробный период скоро закончится</b>\n\n"
        f"До окончания осталось <b>{_format_remaining(remaining)}</b> "
        f"(до <b>{user.subscription_end.strftime('%d.%m.%Y %H:%M')}</b>).\n\n"
        "Чтобы не потерять доступ, оформите подписку в меню бота."
    )
    return await _safe_send(bot, user.id, text, _renew_keyboard())


async def _send_paid_reminder(bot: Bot, user: User, remaining: timedelta) -> bool:
    text = (
        "<tg-emoji emoji-id=\"5258258882022612173\">⏰</tg-emoji> <b>Подписка скоро закончится</b>\n\n"
        f"До окончания осталось <b>{_format_remaining(remaining)}</b> "
        f"(до <b>{user.subscription_end.strftime('%d.%m.%Y %H:%M')}</b>).\n\n"
        "Продлите подписку, чтобы не потерять доступ к VPN."
    )
    return await _safe_send(bot, user.id, text, _renew_keyboard())


async def _safe_send(bot: Bot, user_id: int, text: str, reply_markup=None) -> bool:
    try:
        await bot.send_message(user_id, text, parse_mode="HTML", reply_markup=reply_markup)
        return True
    except TelegramForbiddenError:
        # Пользователь заблокировал бота — напоминания пропускаем
        return False
    except TelegramBadRequest as e:
        logger.warning(f"Reminder BadRequest user={user_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"Reminder send error user={user_id}: {e}")
        return False


async def _process_once(bot: Bot) -> None:
    now = datetime.now()
    horizon = now + PAID_REMINDER_WINDOW

    async with async_session() as session:
        result = await session.execute(
            select(User).where(
                User.is_active.is_(True),
                User.is_banned.is_(False),
                User.subscription_end.isnot(None),
                User.subscription_end > now,
                User.subscription_end <= horizon,
            )
        )
        users = result.scalars().all()

        for user in users:
            remaining = user.subscription_end - now
            last_sent = user.last_reminder_sent_at

            if user.is_trial_subscription:
                if remaining > TRIAL_REMINDER_WINDOW:
                    continue
                if last_sent is not None:
                    continue
                if await _send_trial_reminder(bot, user, remaining):
                    user.last_reminder_sent_at = now
            else:
                if last_sent is not None and (now - last_sent) < PAID_REMINDER_COOLDOWN:
                    continue
                if await _send_paid_reminder(bot, user, remaining):
                    user.last_reminder_sent_at = now

        await session.commit()


async def reminders_loop(bot: Bot) -> None:
    """Запускается в фоне из main.py."""
    # Небольшая задержка после старта, чтобы бот успел подняться
    await asyncio.sleep(60)
    while True:
        try:
            await _process_once(bot)
        except Exception as e:
            logger.error(f"Reminders loop error: {e}", exc_info=True)
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
