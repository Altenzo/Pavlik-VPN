import asyncio
import logging
from aiogram import Bot, Dispatcher
from config import config
from apps.db.database import async_session
from bot.middlewares.db import DbSessionMiddleware
from bot.handlers.start import start_router
from bot.handlers.menu import menu_router

# Настраиваем логирование
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

async def main():
    logger.info("Starting bot...")
    
    # Инициализируем бота и диспетчер
    bot = Bot(token=config.BOT_TOKEN.get_secret_value())
    dp = Dispatcher()
    
    # Регистрируем мидлвари
    dp.update.middleware(DbSessionMiddleware(async_session))

    # Регистрируем роутеры
    dp.include_router(start_router)
    dp.include_router(menu_router)
    
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped!")
