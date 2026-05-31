"""
3x-ui panel API helpers.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

import requests


class X3UIPanel:
    """Small client for the 3x-ui HTTP API."""

    def __init__(self, host: str, port: int, username: str, password: str, use_https: bool = False):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.base_url = f"{'https' if use_https else 'http'}://{host}:{port}"
        self.session = requests.Session()
        self.session.trust_env = False
        if use_https:
            self.session.verify = False

    def login(self) -> bool:
        try:
            response = self.session.post(
                f"{self.base_url}/login",
                data={"username": self.username, "password": self.password},
                timeout=20,
            )
            if response.status_code != 200:
                return False

            data = response.json()
            return bool(data.get("success"))
        except Exception as exc:
            print(f"3x-ui login error on {self.host}: {exc}")
            return False

    def _decode_json_field(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if not value:
            return {}
        try:
            return json.loads(value)
        except Exception:
            return {}

    def _request_with_fallback(self, path: str, payload: dict[str, Any]) -> requests.Response:
        response = self.session.post(f"{self.base_url}{path}", json=payload, timeout=30)
        if response.status_code == 200:
            return response
        return self.session.post(f"{self.base_url}{path}", data=payload, timeout=30)

    def get_inbounds(self) -> list[dict[str, Any]]:
        try:
            response = self.session.get(f"{self.base_url}/panel/api/inbounds/list", timeout=20)
            if response.status_code != 200:
                return []
            data = response.json()
            if not data.get("success"):
                return []
            return data.get("obj", [])
        except Exception as exc:
            print(f"Get inbounds error on {self.host}: {exc}")
            return []

    def get_vless_inbound(self, preferred_port: int = 8443) -> dict[str, Any] | None:
        inbounds = self.get_inbounds()
        for inbound in inbounds:
            if inbound.get("protocol") == "vless" and inbound.get("port") == preferred_port:
                return inbound
        for inbound in inbounds:
            if inbound.get("protocol") == "vless":
                return inbound
        return None

    def add_client(self, email: str, client_id: str, expiry_days: int = 30, traffic_gb: int = 0, limit_ip: int = 0) -> dict[str, Any] | None:
        inbound = self.get_vless_inbound()
        if not inbound:
            print(f"No VLESS inbound found on {self.host}")
            return None

        expiry_time = 0
        if expiry_days > 0:
            expiry_time = int((datetime.now() + timedelta(days=expiry_days)).timestamp() * 1000)

        total_bytes = 0
        if traffic_gb > 0:
            total_bytes = int(traffic_gb * 1024 * 1024 * 1024)

        payload = {
            "id": inbound["id"],
            "settings": json.dumps(
                {
                    "clients": [
                        {
                            "id": client_id,
                            "flow": "xtls-rprx-vision",
                            "email": email,
                            "limitIp": int(limit_ip or 0),
                            "totalGB": total_bytes,
                            "expiryTime": expiry_time,
                            "enable": True,
                            "tgId": "",
                            "subId": "",
                            "reset": 0,
                        }
                    ]
                },
                separators=(",", ":"),
            ),
        }

        try:
            response = self._request_with_fallback("/panel/api/inbounds/addClient", payload)
            data = response.json()
            if not data.get("success"):
                print(f"Add client failed on {self.host}: {data.get('msg')}")
                return None
            return {"uuid": client_id, "email": email, "inbound_id": inbound["id"]}
        except Exception as exc:
            print(f"Add client error on {self.host}: {exc}")
            return None

    def get_client(self, email: str) -> dict[str, Any] | None:
        """Карточка клиента по email (up/down/expiryTime/enable/lastOnline)."""
        try:
            response = self.session.get(
                f"{self.base_url}/panel/api/inbounds/getClientTraffics/{email}", timeout=20
            )
            if response.status_code != 200:
                return None
            data = response.json()
            if not data.get("success"):
                return None
            return data.get("obj")
        except Exception as exc:
            print(f"Get client error on {self.host}: {exc}")
            return None

    def update_client(self, client_id: str, email: str, limit_ip: int,
                      expiry_time: int = 0, total_bytes: int = 0, enable: bool = True) -> bool:
        """Изменить параметры клиента (используется для смены лимита устройств)."""
        inbound = self.get_vless_inbound()
        if not inbound:
            return False
        payload = {
            "id": inbound["id"],
            "settings": json.dumps(
                {
                    "clients": [
                        {
                            "id": client_id,
                            "flow": "xtls-rprx-vision",
                            "email": email,
                            "limitIp": int(limit_ip or 0),
                            "totalGB": int(total_bytes or 0),
                            "expiryTime": int(expiry_time or 0),
                            "enable": bool(enable),
                            "tgId": "",
                            "subId": "",
                            "reset": 0,
                        }
                    ]
                },
                separators=(",", ":"),
            ),
        }
        try:
            response = self._request_with_fallback(
                f"/panel/api/inbounds/updateClient/{client_id}", payload
            )
            return bool(response.json().get("success"))
        except Exception as exc:
            print(f"Update client error on {self.host}: {exc}")
            return False

    def get_online_emails(self) -> list[str]:
        """Список email'ов, у которых прямо сейчас есть активные подключения."""
        try:
            response = self.session.post(f"{self.base_url}/panel/api/inbounds/onlines", timeout=15)
            if response.status_code != 200:
                return []
            data = response.json()
            obj = data.get("obj") or []
            if not isinstance(obj, list):
                return []
            emails: list[str] = []
            for item in obj:
                if isinstance(item, str):
                    emails.append(item)
                elif isinstance(item, dict):
                    # На случай, если панель отдаёт объекты, а не строки.
                    em = item.get("email") or item.get("Email")
                    if em:
                        emails.append(str(em))
            return emails
        except Exception as exc:
            print(f"Onlines error on {self.host}: {exc}")
            return []

    def get_client_ips(self, email: str) -> list[str]:
        """IP-адреса (устройства) клиента из журнала 3x-ui. Пусто, если записей нет.

        Возвращает список РАЗЛИЧНЫХ IP. Если в панели выключен лог IP —
        эндпоинт отдаёт "No IP Record", и список будет пустым.
        """
        try:
            response = self.session.post(
                f"{self.base_url}/panel/api/inbounds/clientIps/{email}", timeout=15
            )
            if response.status_code != 200:
                return []
            obj = response.json().get("obj")
            if not obj or obj == "No IP Record":
                return []

            raw: list[str] = []
            if isinstance(obj, list):
                raw = [str(x) for x in obj]
            elif isinstance(obj, str):
                # Иногда приходит JSON-строкой ('["1.2.3.4","5.6.7.8"]')
                # либо просто строкой с разделителями.
                text = obj.strip()
                parsed = None
                if text.startswith("["):
                    try:
                        parsed = json.loads(text)
                    except Exception:
                        parsed = None
                if isinstance(parsed, list):
                    raw = [str(x) for x in parsed]
                else:
                    raw = [p.strip() for p in text.replace("\n", ",").split(",")]

            # Чистим и убираем дубликаты, сохраняя порядок.
            seen: set[str] = set()
            ips: list[str] = []
            for ip in raw:
                ip = ip.strip().strip('"').strip("[]").strip()
                if ip and ip not in seen:
                    seen.add(ip)
                    ips.append(ip)
            return ips
        except Exception as exc:
            print(f"Client IPs error on {self.host}: {exc}")
            return []

    def get_client_link(self, client_id: str, email: str, domain: str, port: int = 8443) -> str | None:
        inbound = self.get_vless_inbound(preferred_port=port)
        if not inbound:
            return None

        stream_settings = self._decode_json_field(inbound.get("streamSettings") or inbound.get("stream_settings"))
        reality_settings = stream_settings.get("realitySettings", {})
        public_key = reality_settings.get("publicKey", "")
        short_ids = reality_settings.get("shortIds", [])
        server_names = reality_settings.get("serverNames", ["www.google.com"])
        short_id = short_ids[0] if short_ids else ""
        sni = server_names[0] if server_names else "www.google.com"

        # Don't include port 443 in URL (standard HTTPS port)
        if port == 443:
            return (
                f"vless://{client_id}@{domain}?"
                f"flow=xtls-rprx-vision&encryption=none&security=reality&"
                f"sni={sni}&fp=chrome&pbk={public_key}&sid={short_id}&"
                f"type=tcp&headerType=none#{email}"
            )

        return (
            f"vless://{client_id}@{domain}:{port}?"
            f"flow=xtls-rprx-vision&encryption=none&security=reality&"
            f"sni={sni}&fp=chrome&pbk={public_key}&sid={short_id}&"
            f"type=tcp&headerType=none#{email}"
        )

    def delete_client(self, client_id: str) -> bool:
        inbound = self.get_vless_inbound()
        if not inbound:
            return False
        try:
            response = self.session.post(
                f"{self.base_url}/panel/api/inbounds/{inbound['id']}/delClient/{client_id}",
                timeout=20,
            )
            if response.status_code != 200:
                return False
            return bool(response.json().get("success"))
        except Exception as exc:
            print(f"Delete client error on {self.host}: {exc}")
            return False

    def reset_client_traffic(self, client_id: str) -> bool:
        inbound = self.get_vless_inbound()
        if not inbound:
            return False
        try:
            response = self.session.post(
                f"{self.base_url}/panel/api/inbounds/{inbound['id']}/resetClientTraffic/{client_id}",
                timeout=20,
            )
            if response.status_code != 200:
                return False
            return bool(response.json().get("success"))
        except Exception as exc:
            print(f"Reset traffic error on {self.host}: {exc}")
            return False


from config import (
    VPS2_HOST,
    VPS2_3XUI_PASSWORD,
    VPS2_3XUI_PORT,
    VPS2_3XUI_USERNAME,
)


def get_estonia_panel() -> X3UIPanel | None:
    panel = X3UIPanel(
        host=VPS2_HOST,
        port=VPS2_3XUI_PORT,
        username=VPS2_3XUI_USERNAME,
        password=VPS2_3XUI_PASSWORD,
    )
    return panel if panel.login() else None
