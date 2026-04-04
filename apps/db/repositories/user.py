from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from apps.db.models.user import User

async def get_user_by_id(session: AsyncSession, user_id: int) -> User:
    """
    Получает пользователя по его Telegram ID
    """
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()

async def register_user(session: AsyncSession, user_id: int, username: str, full_name: str, referred_by: int = None) -> User:
    """
    Регистрирует нового пользователя в базе
    """
    new_user = User(
        id=user_id,
        username=username,
        full_name=full_name,
        referred_by=referred_by
    )
    session.add(new_user)
    await session.commit()
    await session.refresh(new_user)
    return new_user
