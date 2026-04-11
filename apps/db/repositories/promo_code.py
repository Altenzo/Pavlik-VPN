import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.db.models.promo_code import PromoCode, PromoCodeUsage

logger = logging.getLogger(__name__)


async def create_promo_code(
    session: AsyncSession,
    code: str,
    discount: int,
    created_by: int,
    expires_at: Optional[datetime] = None,
    max_activations: Optional[int] = None,
) -> PromoCode:
    promo = PromoCode(
        code=code.upper(),
        discount=discount,
        created_by=created_by,
        expires_at=expires_at,
        max_activations=max_activations,
    )
    session.add(promo)
    await session.commit()
    await session.refresh(promo)
    logger.info(f"Создан промокод code={code} discount={discount}% by={created_by}")
    return promo


async def get_promo_by_code(session: AsyncSession, code: str) -> Optional[PromoCode]:
    result = await session.execute(
        select(PromoCode).where(PromoCode.code == code.upper())
    )
    return result.scalar_one_or_none()


async def has_user_used_promo(session: AsyncSession, promo_id: int, user_id: int) -> bool:
    result = await session.execute(
        select(PromoCodeUsage).where(
            PromoCodeUsage.promo_code_id == promo_id,
            PromoCodeUsage.user_id == user_id,
        )
    )
    return result.scalar_one_or_none() is not None


async def record_promo_usage(session: AsyncSession, promo_id: int, user_id: int):
    """Записывает факт использования промокода и увеличивает счётчик."""
    promo = await session.get(PromoCode, promo_id)
    if promo:
        promo.current_activations += 1
        usage = PromoCodeUsage(promo_code_id=promo_id, user_id=user_id)
        session.add(usage)
        # Не делаем commit здесь — вызывающий код сам делает commit
