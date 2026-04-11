from sqlalchemy import BigInteger, String, Integer, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from apps.db.models.base import Base
from datetime import datetime
from typing import Optional


class PromoCode(Base):
    __tablename__ = "promo_codes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    discount: Mapped[int] = mapped_column(Integer, nullable=False)  # 10, 20, 50
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    max_activations: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # None = unlimited
    current_activations: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    def __repr__(self) -> str:
        return f"<PromoCode code={self.code} discount={self.discount}%>"


class PromoCodeUsage(Base):
    __tablename__ = "promo_code_usages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    promo_code_id: Mapped[int] = mapped_column(Integer, ForeignKey("promo_codes.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)

    def __repr__(self) -> str:
        return f"<PromoCodeUsage promo={self.promo_code_id} user={self.user_id}>"
