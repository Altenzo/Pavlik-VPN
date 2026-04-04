from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import BigInteger, DateTime, func
from datetime import datetime

class Base(DeclarativeBase):
    """
    Базовый класс для всех моделей.
    """
    # id у каждого будет свой (у кого-то автоинкремент, у кого-то Telegram ID)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, 
        server_default=func.now(), 
        onupdate=func.now()
    )
