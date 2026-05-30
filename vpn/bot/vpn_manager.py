import json
import uuid
from datetime import datetime, timedelta

import paramiko

from config import (
    VPN_NAME,
    VPS2_DOMAIN,
    VPS2_HOST,
    VPS2_PASSWORD,
    VPS2_PORT,
    VPS2_PUBLIC_KEY,
    VPS2_SHORT_ID,
    VPS2_USER,
)
from panel_3xui import get_estonia_panel


class VPNManager:
    """Manages VPN clients on the Estonia server only."""

    def __init__(self, host=None, port=None, user=None, password=None):
        self.host = host or VPS2_HOST
        self.port = port or VPS2_PORT
        self.user = user or VPS2_USER
        self.password = password or VPS2_PASSWORD

    def _connect(self):
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(self.host, username=self.user, password=self.password, timeout=30)
        return client

    def add_user_to_server(self, user_uuid, short_id):
        client = self._connect()
        try:
            config = None
            for path in (
                "/usr/local/etc/xray/config.json",
                "/etc/xray/config.json",
            ):
                stdin, stdout, stderr = client.exec_command(f"cat {path}")
                raw = stdout.read().decode(errors="ignore").strip()
                if not raw:
                    continue
                try:
                    config = json.loads(raw)
                    break
                except Exception:
                    continue

            if not config:
                return False

            new_client = {
                "id": user_uuid,
                "flow": "xtls-rprx-vision",
            }

            clients = config["inbounds"][0]["settings"]["clients"]
            existing_ids = [item["id"] for item in clients]
            if user_uuid in existing_ids:
                return True

            clients.append(new_client)
            config_json = json.dumps(config, indent=2)
            command = f"cat > /usr/local/etc/xray/config.json << 'EOF'\n{config_json}\nEOF"
            client.exec_command(command)
            client.exec_command("systemctl reload xray || systemctl restart xray")
            return True
        finally:
            client.close()

    def remove_user_from_server(self, user_uuid):
        client = self._connect()
        try:
            stdin, stdout, stderr = client.exec_command("cat /usr/local/etc/xray/config.json")
            config = json.loads(stdout.read().decode())

            clients = config["inbounds"][0]["settings"]["clients"]
            config["inbounds"][0]["settings"]["clients"] = [
                client_item for client_item in clients if client_item["id"] != user_uuid
            ]

            config_json = json.dumps(config, indent=2)
            command = f"cat > /usr/local/etc/xray/config.json << 'EOF'\n{config_json}\nEOF"
            client.exec_command(command)
            client.exec_command("systemctl reload xray || systemctl restart xray")
            return True
        finally:
            client.close()

    def _add_client_via_best_method(self, user_uuid, email, days):
        """Add a client to Estonia via 3x-ui API, fall back to SSH config edit."""
        try:
            panel = get_estonia_panel()
            if panel:
                result = panel.add_client(
                    email=email,
                    client_id=user_uuid,
                    expiry_days=days or 0,
                    traffic_gb=0,
                )
                if result:
                    return True
        except Exception as exc:
            print(f"3x-ui error on Estonia ({VPS2_HOST}): {exc}")

        fallback = VPNManager(host=VPS2_HOST, port=VPS2_PORT, user=VPS2_USER, password=VPS2_PASSWORD)
        return fallback.add_user_to_server(user_uuid, VPS2_SHORT_ID)

    def generate_vpn_key(self, user_id, days=None, use_3xui=True):
        user_uuid = str(uuid.uuid4())
        short_id = VPS2_SHORT_ID
        email = f"user_{user_id}_{uuid.uuid4().hex[:8]}@aeroprojectvpn.com"

        expires_at = datetime.now() + timedelta(days=days) if days else None

        estonia_ok = self._add_client_via_best_method(
            user_uuid=user_uuid,
            email=email,
            days=days,
        )

        if not estonia_ok:
            raise RuntimeError("Failed to add client to Estonia VPN server")

        # Build VLESS link for Estonia
        if VPS2_PORT == 443:
            addr = VPS2_DOMAIN
        else:
            addr = f"{VPS2_DOMAIN}:{VPS2_PORT}"

        vless_link = (
            f"vless://{user_uuid}@{addr}?"
            f"flow=xtls-rprx-vision&encryption=none&security=reality&"
            f"sni=www.google.com&fp=chrome&pbk={VPS2_PUBLIC_KEY}&"
            f"sid={short_id}&type=tcp&headerType=none#🇪🇪 Эстония (Fast)"
        )

        return {
            "uuid": user_uuid,
            "public_key": VPS2_PUBLIC_KEY,
            "private_key": "",
            "short_id": short_id,
            "expires_at": expires_at,
            "vless_link": vless_link,
            "server": "estonia",
            "domain": VPS2_DOMAIN,
            "email": email,
            "servers": [
                {
                    "name": "estonia",
                    "host": VPS2_DOMAIN,
                    "port": VPS2_PORT,
                    "public_key": VPS2_PUBLIC_KEY,
                },
            ],
        }

    def remove_key_from_all_servers(self, client_id: str) -> bool:
        """Remove a client from the Estonia server."""
        removed_any = False

        try:
            panel = get_estonia_panel()
            if panel and panel.delete_client(client_id):
                removed_any = True
                print(f"Removed client {client_id} from Estonia")
            else:
                # SSH fallback
                fallback = VPNManager(host=VPS2_HOST, port=VPS2_PORT, user=VPS2_USER, password=VPS2_PASSWORD)
                if fallback.remove_user_from_server(client_id):
                    removed_any = True
                    print(f"Removed client {client_id} from Estonia (SSH fallback)")
        except Exception as exc:
            print(f"Estonia remove error: {exc}")

        return removed_any

    def restart_server(self):
        client = self._connect()
        try:
            client.exec_command("systemctl restart xray || systemctl restart x-ui")
            return True
        finally:
            client.close()

    def get_server_status(self):
        client = self._connect()
        try:
            stdin, stdout, stderr = client.exec_command("systemctl is-active xray || systemctl is-active x-ui")
            status = stdout.read().decode().strip().splitlines()[0]
            return status == "active"
        finally:
            client.close()
