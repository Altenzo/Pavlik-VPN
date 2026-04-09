import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from apps.db.models.transaction import Transaction
from apps.db.models.user import User
from config import config

logger = logging.getLogger(__name__)


async def get_transaction(session: AsyncSession, transaction_id: int) -> Transaction | None:
    return await session.get(Transaction, transaction_id)


async def get_pending_transaction(session: AsyncSession, user_id: int) -> Transaction | None:
    """
    Возвращает открытую (PENDING) транзакцию пользователя, если такая есть.
    Используется для защиты от дублирования — не создаём новую транзакцию,
    пока предыдущая не закрыта.
    """
    stmt = select(Transaction).where(
        Transaction.user_id == user_id,
        Transaction.status == "PENDING"
    ).order_by(Transaction.id.desc()).limit(1)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create_transaction(
    session: AsyncSession,
    user_id: int,
    amount: float,
    tariff_key: str,
    payment_method: str = "sbp"
) -> Transaction:
    """
    Создает запись о транзакции в базе.
    """
    transaction = Transaction(
        user_id=user_id,
        amount=amount,
        tariff_key=tariff_key,
        payment_method=payment_method
    )
    session.add(transaction)
    await session.commit()
    await session.refresh(transaction)
    logger.info(f"Создана транзакция id={transaction.id} user={user_id} amount={amount} tariff={tariff_key}")
    return transaction


async def update_transaction_id(
    session: AsyncSession,
    transaction_id: int,
    external_id: str  # Bug 2 fix: было platega_id — переименовано в external_id
):
    """
    Обновляет внешний ID транзакции (от любой платежки).
    """
    transaction = await session.get(Transaction, transaction_id)
    if transaction:
        transaction.external_id = external_id  # Bug 2 fix: было transaction.platega_id
        await session.commit()


async def update_transaction_status(
    session: AsyncSession,
    transaction_id: int,
    status: str
):
    """
    Обновляет статус транзакции и начисляет бонусы реферерам при успехе.
    Реферальный процент берётся из конфига (Bug 6 fix).
    """
    transaction = await session.get(Transaction, transaction_id)
    if not transaction:
        return

    old_status = transaction.status
    transaction.status = status

    # Реферальные отчисления только при ПЕРВОМ переходе в CONFIRMED
    if status == "CONFIRMED" and old_status != "CONFIRMED":
        user = await session.get(User, transaction.user_id)
        if user and user.referred_by:
            ref1 = await session.get(User, user.referred_by)
            if ref1:
                # Bug 6 fix: процент из конфига, не захардкожен
                commission = transaction.amount * config.REFERRAL_COMMISSION_RATE
                ref1.referral_balance = (ref1.referral_balance or 0.0) + commission
                ref1.total_earned = (ref1.total_earned or 0.0) + commission

    await session.commit()


async def count_pending_transactions(session, user_id: int) -> int:
    """Считает количество открытых PENDING транзакций — лимит 3 штуки."""
    from sqlalchemy import select, func
    result = await session.execute(
        select(func.count(Transaction.id)).where(
            Transaction.user_id == user_id,
            Transaction.status == "PENDING"
        )
    )
    return result.scalar() or 0
