import asyncio
import logging
import logging.handlers
import os
import sys
from datetime import datetime

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter

from config import config
from apps.db.database import async_session
from bot.middlewares.db import DbSessionMiddleware
from bot.middlewares.admin import AdminMiddleware
from bot.handlers.start import start_router
from bot.handlers.menu import menu_router
from bot.handlers.admin import admin_router

# ─── Логирование ────────────────────────────────────────────────
os.makedirs("logs", exist_ok=True)

def setup_logging():
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    # Общий лог
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    root.addHandler(console)

    file_handler = logging.handlers.RotatingFileHandler(
        "logs/bot.log", maxBytes=5*1024*1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    # Лог ошибок
    error_handler = logging.handlers.RotatingFileHandler(
        "logs/bot_errors.log", maxBytes=2*1024*1024, backupCount=3, encoding="utf-8"
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(fmt)
    root.addHandler(error_handler)

setup_logging()
logger = logging.getLogger(__name__)


# ─── Уведомление админов ────────────────────────────────────────
async def notify_admins(bot: Bot, text: str):
    """Отправляет сообщение всем админам. Игнорирует ошибки."""
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text, parse_mode="HTML")
        except Exception as e:
            logger.warning(f"Не удалось уведомить админа {admin_id}: {e}")


# ─── Основная функция ────────────────────────────────────────────
async def main():
    bot = Bot(token=config.BOT_TOKEN.get_secret_value())
    dp = Dispatcher()

    dp.update.middleware(DbSessionMiddleware(async_session))
    dp.update.middleware(AdminMiddleware())

    dp.include_router(admin_router)   # сначала — чтобы админские команды имели приоритет
    dp.include_router(start_router)
    dp.include_router(menu_router)

    return bot, dp


# ─── "Бессмертный" цикл ─────────────────────────────────────────
async def immortal_loop():
    """
    Бесконечный цикл. Бот не умирает ни при каких обстоятельствах.
    При падении — пишет в bot_errors.log, ждёт 5 сек, перезапускается.
    """
    bot, dp = await main()
    first_start = True

    while True:
        try:
            if first_start:
                logger.info("Бот запускается...")
                first_start = False
            else:
                logger.info("Бот перезапускается после ошибки...")

            await dp.start_polling(
                bot,
                allowed_updates=dp.resolve_used_update_types(),
                handle_signals=False,
            )

        except TelegramRetryAfter as e:
            logger.warning(f"Telegram RetryAfter: ждём {e.retry_after} сек...")
            await asyncio.sleep(e.retry_after)

        except TelegramNetworkError as e:
            msg = f"⚠️ <b>Сетевая ошибка Telegram:</b>\n<code>{e}</code>"
            logger.error(f"TelegramNetworkError: {e}")
            await notify_admins(bot, msg)
            await asyncio.sleep(5)

        except Exception as e:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            err_text = f"[{ts}] CRASH: {type(e).__name__}: {e}"

            # Пишем в bot_errors.log
            with open("logs/bot_errors.log", "a", encoding="utf-8") as f:
                f.write(err_text + "\n")

            logger.error(f"Бот упал: {e}", exc_info=True)

            # Уведомляем всех админов
            admin_msg = (
                f"🔴 <b>Бот упал и перезапускается!</b>\n\n"
                f"<b>Время:</b> {ts}\n"
                f"<b>Ошибка:</b> <code>{type(e).__name__}: {e}</code>"
            )
            await notify_admins(bot, admin_msg)
            await asyncio.sleep(5)


if __name__ == "__main__":
    try:
        asyncio.run(immortal_loop())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен вручную.")
