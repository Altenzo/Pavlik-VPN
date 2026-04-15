import aiohttp
import logging
import time
import uuid
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class PlategaService:
    """
    Бэкенд-сервис для работы с платежной системой Platega.io
    """
    def __init__(self, merchant_id: str, secret_key: str):
        self.merchant_id = merchant_id
        self.secret_key = secret_key
        self.base_url = "https://app.platega.io"
        
        self.headers = {
            "X-MerchantId": self.merchant_id,
            "X-Secret": self.secret_key,
            "Content-Type": "application/json"
        }

    async def create_transaction(
        self,
        amount: float,
        description: str,
        order_id: str,
        currency: str = "RUB",
        payment_method: int = 2  # 2 - СБП по умолчанию
    ) -> Optional[Dict[str, Any]]:
        """
        Создает транзакцию и возвращает ссылку на оплату
        """
        endpoint = f"{self.base_url}/transaction/process"

        # Platega expects id as a valid UUID; derive one deterministically from order_id
        order_uuid = str(uuid.uuid5(uuid.NAMESPACE_OID, str(order_id)))

        payload = {
            "command": "process",
            "id": order_uuid,
            "paymentMethod": payment_method,
            "paymentDetails": {
                "amount": amount,
                "currency": currency
            },
            "description": f"{description} (Заказ #{order_id})",
            "callbackUrl": "https://bot.svinn.mooo.com/platega-webhook",
            "returnUrl": "https://t.me/blago_vpn_news",
            "failedUrl": "https://t.me/blago_vpn_news"
        }

        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            try:
                # Отладочный лог заголовков (маскируем секрет)
                masked_headers = {k: (v[:4] + "***" if "secret" in k.lower() or "key" in k.lower() else v) for k, v in self.headers.items()}
                logger.info(f"Sending request to Platega. Endpoint: {endpoint}. Headers: {masked_headers}")

                async with session.post(endpoint, json=payload, headers=self.headers) as response:
                    response_text = await response.text()
                    try:
                        import json as _json
                        response_json = _json.loads(response_text)
                    except Exception:
                        response_json = {"raw_error": response_text}

                    if response.status == 200:
                        return response_json
                    
                    logger.error(f"Platega API Error (Status {response.status}): {response_json}")
                    return None
            except Exception as e:
                logger.error(f"Platega Connection Fatal Error: {e}")
                return None

    async def check_status(self, transaction_id: str) -> Optional[str]:
        """
        Проверяет статус транзакции по её ID
        Возвращает: 'CONFIRMED', 'PENDING', 'CANCELED' и др.
        """
        endpoint = f"{self.base_url}/transaction/{transaction_id}"

        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            try:
                async with session.get(endpoint, headers=self.headers) as response:
                    response_text = await response.text()
                    logger.info(f"Platega check_status tx={transaction_id}: HTTP {response.status}, body={response_text[:200]}")
                    if response.status == 200:
                        try:
                            import json as _json
                            data = _json.loads(response_text)
                        except Exception:
                            logger.error(f"Platega check_status: не удалось распарсить JSON: {response_text[:200]}")
                            return None
                        status = data.get("status")
                        logger.info(f"Platega check_status tx={transaction_id}: статус={status}")
                        return status
                    logger.error(f"Platega check_status: HTTP {response.status}, body={response_text[:200]}")
                    return None
            except Exception as e:
                logger.error(f"Platega status check error tx={transaction_id}: {e}")
                return None
