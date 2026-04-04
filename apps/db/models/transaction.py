from sqlalchemy import BigInteger, String, Float, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from apps.db.models.base import Base
from datetime import datetime

class Transaction(Base):
    """
    Универсальная модель транзакции (Best Practice)
    """
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    
    # Сумма и валюта
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(10), default="RUB")
    
    # Универсальные данные платежа
    external_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=True) # ID в любой платежке
    payment_method: Mapped[str] = mapped_column(String(20), default="sbp") # sbp, crypto
    provider: Mapped[str] = mapped_column(String(50), default="platega") # platega, hellcat
    
    status: Mapped[str] = mapped_column(String(50), default="PENDING")
    tariff_key: Mapped[str] = mapped_column(String(50))
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    def __repr__(self) -> str:
        return f"<Transaction id={self.id} method={self.payment_method} amount={self.amount}>"
