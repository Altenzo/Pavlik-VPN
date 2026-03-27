from sqlalchemy import BigInteger, String, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from apps.db.models.base import Base
from datetime import datetime
from typing import Optional

class User(Base):
    """
    Модель пользователя бота
    """
    __tablename__ = "users"

    # Telegram ID (храним как BigInteger, т.к. ID могут быть очень длинными)
    user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    
    # Данные из телеграма
    username: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    full_name: Mapped[str] = mapped_column(String(255))
    
    # Поля VPN-сервиса
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    subscription_end: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Ссылка на VLESS (будем хранить её здесь после создания в панели)
    vless_link: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)

    def __repr__(self) -> str:
        return f"<User user_id={self.user_id} full_name='{self.full_name}'>"
