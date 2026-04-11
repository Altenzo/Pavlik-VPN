import asyncio
import logging
import logging.handlers
import os
import sys
from datetime import datetime

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter

from sqlalchemy import select
from config import config
from apps.db.database import async_session
from apps.db.models.transaction import Transaction
from bot.middlewares.db import DbSessionMiddleware
from bot.middlewares.admin import AdminMiddleware
from bot.middlewares.ban import BanMiddleware
from bot.handlers.start import start_router
from bot.handlers.menu import menu_router
from bot.handlers.admin import admin_router

# ─── Логирование ────────────────────────────────────────────────
os.makedirs("logs", exist_ok=True)

def setup_logging():
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

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
    dp.update.middleware(BanMiddleware())

    dp.include_router(admin_router)
    dp.include_router(start_router)
    dp.include_router(menu_router)

    # Фоновый watchdog — проверяет все PENDING платежи каждые 5 минут
    asyncio.create_task(_payment_watchdog(bot))

    # Восстанавливаем проверку платежей для PENDING транзакций после рестарта
    async with async_session() as session:
        result = await session.execute(
            select(Transaction).where(Transaction.status == "PENDING")
        )
        pending = result.scalars().all()
        for tx in pending:
            if tx.external_id:
                logger.info(f"Восстанавливаем проверку платежа tx={tx.id} external_id={tx.external_id}")
                asyncio.create_task(
                    _auto_confirm_payment_by_id(bot, tx.id, tx.external_id)
                )

    return bot, dp


async def _payment_watchdog(bot: Bot):
    """Каждые 5 минут проверяет все PENDING транзакции."""
    from apps.services.payment.platega_service import PlategaService
    from bot.handlers.menu import _activate_subscription_after_payment
    from apps.db.repositories.transaction import update_transaction_status

    platega = PlategaService(config.PLATEGA_MERCHANT_ID, config.PLATEGA_SECRET)

    while True:
        await asyncio.sleep(300)
        try:
            async with async_session() as session:
                result = await session.execute(
                    select(Transaction).where(
                        Transaction.status == "PENDING",
                        Transaction.external_id.isnot(None),
                    )
                )
                pending = result.scalars().all()

            for tx in pending:
                try:
                    status = await platega.check_status(tx.external_id)
                    if status == "CONFIRMED":
                        async with async_session() as session:
                            await _activate_subscription_after_payment(session, tx.id)
                        logger.info(f"Watchdog: подтверждён платёж tx={tx.id}")
                        try:
                            await bot.send_message(
                                tx.user_id,
                                "<tg-emoji emoji-id=\"5260341314095947411\">✅</tg-emoji> <b>Оплата подтверждена!</b>\n"
                                "Ваша подписка активирована. Ссылку ищите в Профиле → Мои подписки.",
                                parse_mode="HTML"
                            )
                        except Exception:
                            pass
                    elif status in ("CANCELED", "FAILED", "EXPIRED"):
                        async with async_session() as session:
                            await update_transaction_status(session, tx.id, status)
                        logger.info(f"Watchdog: платёж tx={tx.id} → {status}")
                except Exception as e:
                    logger.error(f"Watchdog: ошибка проверки tx={tx.id}: {e}")
        except Exception as e:
            logger.error(f"Watchdog: критическая ошибка: {e}", exc_info=True)


async def _auto_confirm_payment_by_id(bot: Bot, tx_id: int, external_id: str):
    """Восстанавливает проверку платежа после рестарта бота."""
    from apps.services.payment.platega_service import PlategaService
    from bot.handlers.menu import _activate_subscription_after_payment
    from apps.db.repositories.transaction import update_transaction_status

    platega = PlategaService(config.PLATEGA_MERCHANT_ID, config.PLATEGA_SECRET)

    for _ in range(30):
        await asyncio.sleep(20)
        try:
            status = await platega.check_status(external_id)
        except Exception as e:
            logger.error(f"check_status error tx={tx_id}: {e}")
            continue

        if status == "CONFIRMED":
            async with async_session() as session:
                await _activate_subscription_after_payment(session, tx_id)
            try:
                for admin_id in config.ADMIN_IDS:
                    await bot.send_message(
                        admin_id,
                        f"✅ Платёж <code>{tx_id}</code> подтверждён после рестарта бота.",
                        parse_mode="HTML"
                    )
            except Exception:
                pass
            return

        if status in ("CANCELED", "FAILED"):
            async with async_session() as session:
                await update_transaction_status(session, tx_id, status)
            return

    async with async_session() as session:
        await update_transaction_status(session, tx_id, "EXPIRED")


# ─── "Бессмертный" цикл ─────────────────────────────────────────
async def immortal_loop():
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

            with open("logs/bot_errors.log", "a", encoding="utf-8") as f:
                f.write(err_text + "\n")

            logger.error(f"Бот упал: {e}", exc_info=True)

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
