import aiohttp
import base64
import hashlib
import json
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


# Карта сырых статусов Heleket → внутренние статусы транзакции.
# PENDING используется как дефолт для любых промежуточных состояний.
HELEKET_STATUS_MAP: Dict[str, str] = {
    "paid": "CONFIRMED",
    "paid_over": "CONFIRMED",
    "wrong_amount": "FAILED",
    "wrong_amount_waiting": "PENDING",
    "cancel": "CANCELED",
    "fail": "FAILED",
    "system_fail": "FAILED",
    "refund_process": "CANCELED",
    "refund_paid": "CANCELED",
    "refund_fail": "CANCELED",
    "locked": "PENDING",
    "wait_payment": "PENDING",
    "check": "PENDING",
    "process": "PENDING",
    "confirm_check": "PENDING",
    "expired": "EXPIRED",
}


class HeleketService:
    """
    Клиент API Heleket (платежи в криптовалюте).
    Документация: https://doc.heleket.com/ru
    API совместимо с Cryptomus: подпись = md5(base64(body) + api_key).
    """

    BASE_URL = "https://api.heleket.com/v1"

    def __init__(self, merchant_id: str, api_key: str):
        self.merchant_id = merchant_id
        self.api_key = api_key

    def _sign(self, body_str: str) -> str:
        b64 = base64.b64encode(body_str.encode("utf-8")).decode("utf-8")
        return hashlib.md5((b64 + self.api_key).encode("utf-8")).hexdigest()

    def _headers(self, body_str: str) -> Dict[str, str]:
        return {
            "merchant": self.merchant_id,
            "sign": self._sign(body_str),
            "Content-Type": "application/json",
        }

    async def _post(self, path: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        body = json.dumps(payload)
        url = f"{self.BASE_URL}{path}"
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            try:
                async with session.post(url, data=body, headers=self._headers(body)) as resp:
                    text = await resp.text()
                    try:
                        data = json.loads(text)
                    except Exception:
                        logger.error(f"Heleket {path}: ответ не JSON: {text[:300]}")
                        return None

                    if resp.status != 200 or str(data.get("state")) != "0":
                        logger.error(
                            f"Heleket {path} API error: HTTP {resp.status}, body={text[:300]}"
                        )
                        return None

                    return data.get("result")
            except Exception as e:
                logger.error(f"Heleket {path}: ошибка соединения: {e}")
                return None

    async def create_transaction(
        self,
        amount: float,
        description: str,
        order_id: str,
        currency: str = "RUB",
        callback_url: Optional[str] = None,
        return_url: str = "https://t.me/blago_vpn_news",
        success_url: str = "https://t.me/blago_vpn_news",
        lifetime: int = 1800,
    ) -> Optional[Dict[str, Any]]:
        """
        Создаёт инвойс. Возвращает словарь с полями uuid, url, order_id, amount и т.п.
        """
        payload: Dict[str, Any] = {
            "amount": f"{amount:.2f}",
            "currency": currency,
            "order_id": str(order_id),
            "url_return": return_url,
            "url_success": success_url,
            "lifetime": lifetime,
            "additional_data": description,
        }
        if callback_url:
            payload["url_callback"] = callback_url

        result = await self._post("/payment", payload)
        if not result:
            return None

        logger.info(
            f"Heleket: инвойс создан uuid={result.get('uuid')} order_id={order_id} amount={amount} {currency}"
        )
        return result

    async def check_status(self, uuid: str) -> Optional[str]:
        """
        Возвращает нормализованный статус ('CONFIRMED', 'PENDING', 'CANCELED', 'FAILED', 'EXPIRED')
        или None, если запрос не удался.
        """
        result = await self._post("/payment/info", {"uuid": uuid})
        if not result:
            return None
        raw = str(result.get("payment_status") or result.get("status") or "").lower()
        mapped = HELEKET_STATUS_MAP.get(raw, "PENDING")
        logger.info(f"Heleket check_status uuid={uuid}: raw={raw} → {mapped}")
        return mapped

    def verify_webhook(self, body: Dict[str, Any]) -> bool:
        """
        Проверяет подпись callback'а. Heleket шлёт JSON с полем `sign`;
        корректная подпись = md5(base64(тело_без_sign) + api_key).
        Пробуем оба варианта сериализации (с пробелами и компактный) —
        на практике совпадает один из них.
        """
        sign = body.get("sign")
        if not sign:
            return False

        data = {k: v for k, v in body.items() if k != "sign"}
        for kwargs in ({}, {"separators": (",", ":")}):
            body_str = json.dumps(data, **kwargs)
            if self._sign(body_str) == sign:
                return True
        return False
