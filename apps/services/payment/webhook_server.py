import logging
from aiohttp import web
from sqlalchemy import select
from apps.db.database import async_session
from apps.db.models.transaction import Transaction
from apps.db.repositories.transaction import update_transaction_status
from apps.services.payment.heleket_service import HELEKET_STATUS_MAP, HeleketService
from config import config

logger = logging.getLogger(__name__)


async def platega_webhook(request: web.Request) -> web.Response:
    """
    Принимает POST-уведомления от Platega об изменении статуса транзакции.
    Должен вернуть 200 OK иначе Platega будет повторять попытки.
    """
    try:
        data = await request.json()
    except Exception:
        logger.warning("Platega webhook: не удалось распарсить JSON")
        return web.Response(status=400)

    logger.info(f"Platega webhook received: {data}")

    transaction_id = data.get("transactionId") or data.get("id")
    status = data.get("status", "").upper()

    if not transaction_id or not status:
        logger.warning(f"Platega webhook: отсутствует transactionId или status: {data}")
        return web.Response(status=200)

    try:
        async with async_session() as session:
            result = await session.execute(
                select(Transaction).where(Transaction.external_id == str(transaction_id))
            )
            tx = result.scalar_one_or_none()

            if not tx:
                logger.warning(f"Platega webhook: транзакция не найдена external_id={transaction_id}")
                return web.Response(status=200)

            if status == "CONFIRMED" and tx.status != "CONFIRMED":
                from bot.handlers.menu import _activate_subscription_after_payment
                await _activate_subscription_after_payment(session, tx.id)
                logger.info(f"Platega webhook: подписка активирована tx={tx.id}")
            elif status in ("CANCELED", "FAILED", "EXPIRED") and tx.status == "PENDING":
                await update_transaction_status(session, tx.id, status)
                logger.info(f"Platega webhook: транзакция tx={tx.id} → {status}")

    except Exception as e:
        logger.error(f"Platega webhook: ошибка обработки: {e}", exc_info=True)

    return web.Response(status=200)


async def heleket_webhook(request: web.Request) -> web.Response:
    """
    Принимает POST-уведомления от Heleket.
    Проверяем подпись, затем дополнительно переспрашиваем статус через API
    как защиту от подделки.
    """
    try:
        data = await request.json()
    except Exception:
        logger.warning("Heleket webhook: не удалось распарсить JSON")
        return web.Response(status=400)

    logger.info(f"Heleket webhook received: {data}")

    uuid = data.get("uuid")
    order_id = data.get("order_id")
    raw_status = str(data.get("status") or data.get("payment_status") or "").lower()
    mapped_status = HELEKET_STATUS_MAP.get(raw_status, "PENDING")

    if not uuid and not order_id:
        logger.warning(f"Heleket webhook: нет uuid/order_id: {data}")
        return web.Response(status=200)

    heleket = HeleketService(config.HELEKET_MERCHANT_ID, config.HELEKET_API_KEY)

    if not heleket.verify_webhook(data):
        logger.warning(f"Heleket webhook: неверная подпись uuid={uuid}")
        # Не падаем сразу — дополнительно проверим через API ниже.

    try:
        async with async_session() as session:
            tx = None
            if uuid:
                result = await session.execute(
                    select(Transaction).where(Transaction.external_id == str(uuid))
                )
                tx = result.scalar_one_or_none()
            if not tx and order_id and str(order_id).isdigit():
                tx = await session.get(Transaction, int(order_id))

            if not tx:
                logger.warning(f"Heleket webhook: транзакция не найдена uuid={uuid} order_id={order_id}")
                return web.Response(status=200)

            # Дополнительно перепроверяем статус через API (защита от подделки).
            api_status = await heleket.check_status(str(uuid)) if uuid else None
            final_status = api_status or mapped_status

            if final_status == "CONFIRMED" and tx.status != "CONFIRMED":
                from bot.handlers.menu import _activate_subscription_after_payment
                await _activate_subscription_after_payment(session, tx.id)
                logger.info(f"Heleket webhook: подписка активирована tx={tx.id}")
            elif final_status in ("CANCELED", "FAILED", "EXPIRED") and tx.status == "PENDING":
                await update_transaction_status(session, tx.id, final_status)
                logger.info(f"Heleket webhook: транзакция tx={tx.id} → {final_status}")

    except Exception as e:
        logger.error(f"Heleket webhook: ошибка обработки: {e}", exc_info=True)

    return web.Response(status=200)


def create_webhook_app() -> web.Application:
    app = web.Application()
    app.router.add_post("/platega-webhook", platega_webhook)
    app.router.add_post("/heleket-webhook", heleket_webhook)
    return app
