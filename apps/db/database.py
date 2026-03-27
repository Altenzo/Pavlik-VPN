from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from config import config

# Создаем движок (Engine) — это наш основной канал связи с Postgres
# Мы используем asyncpg — самый быстрый асинхронный драйвер для Python
engine = create_async_engine(
    url=config.db_url,
    echo=True, # Оставляем True на этапе разработки, чтобы видеть SQL-запросы в консоли
)

# Создаем фабрику сессий — это как "кран", который открывает доступ к БД для каждого запроса
async_session = async_sessionmaker(
    engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)

async def get_session() -> AsyncSession:
    """
    Генератор сессий для использования в хендлерах или миддлварях
    """
    async with async_session() as session:
        yield session
