import aiohttp
import logging
import json
from datetime import datetime, timedelta, timezone
from typing import Optional, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class VpnDevice:
    hwid: str
    platform: str
    device_model: str
    user_agent: str
    created_at: Optional[datetime]


@dataclass
class VpnUser:
    uuid: str
    username: str
    subscription_url: str
    expire_at: datetime
    traffic_limit_bytes: int
    used_traffic_bytes: int = 0
    lifetime_used_traffic_bytes: int = 0
    online_at: Optional[datetime] = None
    status: str = ""


class RemnawaveService:

    def __init__(self, panel_url: str, api_token: str, inbound_uuid: str = "",
                 internal_squad_uuids: Optional[List[str]] = None,
                 external_squad_uuid: Optional[str] = None):
        self.panel_url = panel_url.rstrip("/")
        self.api_token = api_token
        self.internal_squad_uuids = internal_squad_uuids or []
        self.external_squad_uuid = external_squad_uuid
        self._headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        }

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        url = f"{self.panel_url}{path}"
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.request(method, url, headers=self._headers, **kwargs) as r:
                text = await r.text()
                if r.status >= 400:
                    raise RuntimeError(f"Remnawave {method} {path} → {r.status}: {text}")
                return json.loads(text)

    async def create_user(self, telegram_id: int, days: int, traffic_limit_gb: float = 0) -> Optional[VpnUser]:
        try:
            expire_dt_utc = datetime.now(timezone.utc) + timedelta(days=days)
            expire_iso = expire_dt_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z")

            traffic_bytes = int(traffic_limit_gb * 1024 ** 3) if traffic_limit_gb > 0 else 0

            payload = {
                "username": f"tg_{telegram_id}",
                "trafficLimitBytes": traffic_bytes,
                "trafficLimitStrategy": "NO_RESET",
                "expireAt": expire_iso,
                "description": f"Telegram ID: {telegram_id}",
            }

            if self.internal_squad_uuids:
                payload["activeInternalSquads"] = self.internal_squad_uuids
            if self.external_squad_uuid:
                payload["externalSquadUuid"] = self.external_squad_uuid

            data = await self._request("POST", "/api/users", json=payload)
            user = self._parse(data.get("response", data))
            logger.info(f"Remnawave: создан юзер uuid={user.uuid} sub={user.subscription_url}")
            return user

        except Exception as e:
            logger.error(f"Remnawave create_user(tg={telegram_id}) FAILED: {e}", exc_info=True)
            return None

    async def extend_user(self, vpn_uuid: str, new_expire_dt: datetime) -> bool:
        try:
            # Убираем tzinfo если есть — API ждёт UTC ISO строку
            naive_dt = new_expire_dt.replace(tzinfo=None)
            expire_iso = naive_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
            await self._request("PATCH", f"/api/users/{vpn_uuid}", json={"expireAt": expire_iso})
            return True
        except Exception as e:
            logger.error(f"Remnawave extend_user(uuid={vpn_uuid}): {e}")
            return False

    async def revoke_subscription(self, vpn_uuid: str) -> Optional[VpnUser]:
        try:
            data = await self._request("POST", f"/api/users/{vpn_uuid}/actions/revoke")
            return self._parse(data.get("response", data))
        except Exception as e:
            logger.error(f"Remnawave revoke_subscription(uuid={vpn_uuid}): {e}")
            return None

    async def get_user(self, vpn_uuid: str) -> Optional[VpnUser]:
        try:
            data = await self._request("GET", f"/api/users/{vpn_uuid}")
            return self._parse(data.get("response", data))
        except Exception as e:
            logger.error(f"Remnawave get_user(uuid={vpn_uuid}): {e}")
            return None

    async def get_user_devices(self, vpn_uuid: str) -> List[VpnDevice]:
        try:
            data = await self._request("GET", f"/api/hwid/devices/{vpn_uuid}")
            payload = data.get("response", data)
            if isinstance(payload, dict):
                items = payload.get("devices") or payload.get("data") or []
            elif isinstance(payload, list):
                items = payload
            else:
                items = []
            return [self._parse_device(d) for d in items if isinstance(d, dict)]
        except Exception as e:
            logger.warning(f"Remnawave get_user_devices(uuid={vpn_uuid}): {e}")
            return []

    def _parse_device(self, d: dict) -> VpnDevice:
        raw_created = d.get("createdAt") or d.get("created_at") or ""
        created_dt: Optional[datetime] = None
        try:
            if raw_created:
                created_dt = datetime.fromisoformat(raw_created.replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            created_dt = None

        return VpnDevice(
            hwid=d.get("hwid") or d.get("id") or "",
            platform=d.get("platform") or d.get("os") or "",
            device_model=d.get("deviceModel") or d.get("device_model") or d.get("model") or "",
            user_agent=d.get("userAgent") or d.get("user_agent") or "",
            created_at=created_dt,
        )

    async def delete_user(self, vpn_uuid: str) -> bool:
        try:
            await self._request("DELETE", f"/api/users/{vpn_uuid}")
            return True
        except Exception as e:
            logger.error(f"Remnawave delete_user(uuid={vpn_uuid}): {e}")
            return False

    def _parse(self, d: dict) -> VpnUser:
        uuid = d.get("uuid") or d.get("id", "")
        sub_url = (
            d.get("subscriptionUrl")
            or d.get("subscription_url")
            or d.get("subUrl")
            or f"{self.panel_url}/sub/{d.get('shortUuid', uuid)}"
        )
        raw_expire = d.get("expireAt") or ""
        try:
            expire_dt = datetime.fromisoformat(raw_expire.replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            expire_dt = datetime.now(timezone.utc).replace(tzinfo=None)

        raw_online = d.get("onlineAt") or d.get("lastOnlineAt") or ""
        online_dt: Optional[datetime] = None
        try:
            if raw_online:
                online_dt = datetime.fromisoformat(raw_online.replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            online_dt = None

        return VpnUser(
            uuid=uuid,
            username=d.get("username", ""),
            subscription_url=sub_url,
            expire_at=expire_dt,
            traffic_limit_bytes=d.get("trafficLimitBytes") or 0,
            used_traffic_bytes=d.get("usedTrafficBytes") or d.get("used_traffic_bytes") or 0,
            lifetime_used_traffic_bytes=(
                d.get("lifetimeUsedTrafficBytes")
                or d.get("lifetime_used_traffic_bytes")
                or 0
            ),
            online_at=online_dt,
            status=d.get("status") or "",
        )


def format_bytes(n: int) -> str:
    if not n or n <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(n)
    i = 0
    while size >= 1024 and i < len(units) - 1:
        size /= 1024
        i += 1
    if i == 0:
        return f"{int(size)} {units[i]}"
    return f"{size:.2f} {units[i]}"
