from sqlalchemy import BigInteger, String, Boolean, DateTime, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column
from apps.db.models.base import Base
from datetime import datetime
from typing import Optional


class User(Base):
    """
    Модель пользователя бота.
    id = Telegram ID (не autoincrement).
    """
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)

    # Данные из Telegram
    username: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    full_name: Mapped[str] = mapped_column(String(255))

    # VPN-подписка
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    subscription_end: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # UUID пользователя в Remnawave панели (нужен для продления/удаления)
    vpn_uuid: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Ссылка на подписку (vless:// или sub-ссылка Remnawave)
    vless_link: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)

    # Реферальная система
    referred_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    trial_used: Mapped[bool] = mapped_column(Boolean, default=False)
    referral_balance: Mapped[float] = mapped_column(Float, default=0.0)
    total_earned: Mapped[float] = mapped_column(Float, default=0.0)

    # Блокировка
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    ban_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Активный промокод (применяется при следующей покупке)
    active_promo_code_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Язык интерфейса
    language: Mapped[str] = mapped_column(String(10), default="ru", server_default="ru")

    def __repr__(self) -> str:
        return f"<User id={self.id} full_name='{self.full_name}'>"
