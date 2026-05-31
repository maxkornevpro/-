"""
AeroProjectVPN Subscription API
Generates subscription files for Happ app and other v2ray clients
Uses encrypted tokens instead of plain user IDs
Built-in http.server (no Flask dependency)
"""

import sqlite3
import json
import copy
import base64
import html
import time
from collections import defaultdict, deque
from pathlib import Path
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, quote
from urllib.request import Request, urlopen

import sys
sys.path.insert(0, "/opt/aeroprojectvpn/bot")

from config import (
    DB_FILE,
    SUBSCRIPTION_BASE_URL,
    VPN_NAME,
    VPS2_DOMAIN,
    VPS2_PORT,
    VPS2_PUBLIC_KEY,
    VPS2_SHORT_ID,
)
from token_crypto import decrypt_token, encrypt_user_id


# ==================== RATE-LIMIT (защита от перебора токенов) ====================
# Журнал доступа выключен в log_message, поэтому ограничиваем частоту сами.
_RL_HITS = defaultdict(deque)
_RL_LIMIT = 120          # запросов
_RL_WINDOW = 60          # за столько секунд с одного IP


def _rl_client_ip(handler):
    xff = handler.headers.get('X-Forwarded-For')
    if xff:
        return xff.split(',')[0].strip()
    return handler.headers.get('X-Real-IP') or handler.client_address[0]


def _rl_allow(ip):
    now = time.monotonic()
    dq = _RL_HITS[ip]
    while dq and now - dq[0] > _RL_WINDOW:
        dq.popleft()
    if len(dq) >= _RL_LIMIT:
        return False
    dq.append(now)
    if len(_RL_HITS) > 5000:
        _RL_HITS.clear()
    return True


# Server configurations - Estonia only
SERVERS = {
    'estonia': {
        'name': 'Эстония (Fast)',
        'flag': '🇪🇪',
        'host': VPS2_DOMAIN,
        'port': VPS2_PORT,
        'public_key': VPS2_PUBLIC_KEY,
        'short_id': VPS2_SHORT_ID,
        'server_name': 'www.google.com',
        'primary': True,
    },
}

SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_DIRS = (
    SCRIPT_DIR.parent / 'кфгшки',
    SCRIPT_DIR / 'кфгшки',
)
INTERNAL_CONFIG_FILENAMES = ('obhod-glushilok-i.json', 'obhod-glushilok.json')

BYPASS_CONFIGS = {
    'obhod-glushilok.json': {
        'name': '🇷🇺 Обход глушилок II',
        'config': lambda: {
            "dns": {
                "tag": "dns-in",
                "servers": ["8.8.8.8", "9.9.9.9"],
                "queryStrategy": "UseIPv4",
            },
            "log": {"loglevel": "warning"},
            "routing": {
                "rules": [
                    {
                        "type": "field",
                        "protocol": ["bittorrent"],
                        "outboundTag": "direct",
                    },
                    {
                        "type": "field",
                        "domain": [
                            "domain:bps-sberbank.by",
                            "domain:sber-bank.by",
                            "domain:sber.ru",
                            "domain:sberbank.com",
                            "domain:sberbank.ru",
                            "domain:sbrf.ru",
                        ],
                        "outboundTag": "proxy",
                    },
                    {
                        "type": "field",
                        "domain": [
                            "domain:tbank.ru",
                            "domain:t-bank-app.ru",
                            "domain:tinkoff.ru",
                            "domain:tcsbank.ru",
                            "domain:rosbank.ru",
                            "domain:t-bank.by",
                            "domain:tbank-online.com",
                            "domain:cdn-tinkoff.ru",
                            "domain:my-tbank.ru",
                        ],
                        "outboundTag": "proxy",
                    },
                    {
                        "type": "field",
                        "domain": [
                            "domain:mtalk.google.com",
                            "domain:push.apple.com",
                            "domain:api.push.apple.com",
                            "domain:push-apple.com.akadns.net",
                            "domain:courier.push.apple.com",
                            "domain:mangabuff.ru",
                            "domain:yandex.com",
                            "domain:yandex.net",
                            "domain:mail.ru",
                            "domain:vk.com",
                            "domain:vkusvill.ru",
                            "domain:ozon.ru",
                            "domain:wildberries.ru",
                            "domain:sberbank.ru",
                            "domain:tinkoff.ru",
                            "domain:gosuslugi.ru",
                            "domain:nalog.gov.ru",
                            "domain:mos.ru",
                            "domain:2gis.com",
                            "domain:2gis.ru",
                        ],
                        "outboundTag": "direct",
                    },
                    {
                        "ip": ["17.0.0.0/8"],
                        "type": "field",
                        "outboundTag": "direct",
                    },
                    {
                        "type": "field",
                        "domain": [
                            "domain:2ip.ru",
                            "domain:2ip.io",
                            "habr.com",
                            "4pda.to",
                            "4pda.ru",
                            "kemono.su",
                            "jut.su",
                            "kara.su",
                            "theins.ru",
                            "tvrain.ru",
                            "echo.msk.ru",
                            "the-village.ru",
                            "snob.ru",
                            "novayagazeta.ru",
                            "moscowtimes.ru",
                        ],
                        "outboundTag": "proxy",
                    },
                    {
                        "type": "field",
                        "domain": ["geosite:private", "geosite:category-ru"],
                        "outboundTag": "direct",
                    },
                    {
                        "ip": ["geoip:ru", "geoip:private"],
                        "type": "field",
                        "outboundTag": "direct",
                    },
                ],
                "domainStrategy": "IPIfNonMatch",
            },
            "inbounds": [
                {
                    "tag": "socks",
                    "port": 10808,
                    "listen": "127.0.0.1",
                    "protocol": "socks",
                    "settings": {"udp": True, "auth": "noauth"},
                    "sniffing": {
                        "enabled": True,
                        "destOverride": ["http", "tls", "quic"],
                    },
                },
                {
                    "tag": "http",
                    "port": 10809,
                    "listen": "127.0.0.1",
                    "protocol": "http",
                    "settings": {"allowTransparent": False},
                    "sniffing": {
                        "enabled": True,
                        "destOverride": ["http", "tls", "quic"],
                    },
                },
            ],
            "outbounds": [
                {
                    "tag": "proxy",
                    "protocol": "vless",
                    "settings": {
                        "vnext": [
                            {
                                "address": "51.250.18.219",
                                "port": 443,
                                "users": [
                                    {
                                        "id": "0145aa69-a27d-4126-bb14-90dcefc8cc28",
                                        "encryption": "none",
                                        "flow": "xtls-rprx-vision",
                                    }
                                ],
                            }
                        ]
                    },
                    "streamSettings": {
                        "network": "tcp",
                        "tcpSettings": {},
                        "security": "reality",
                        "realitySettings": {
                            "serverName": "ads.x5.ru",
                            "publicKey": "oqRus6Z_Q1jqJaTEPu7ENbRL0-XKOw54K0jwCCGLtEk",
                            "shortId": "5d8e1a9c4f72b3",
                            "fingerprint": "chrome",
                        },
                    },
                },
                {"tag": "direct", "protocol": "freedom"},
                {"tag": "block", "protocol": "blackhole"},
            ],
            "remarks": "🇷🇺 Обход глушилок II",
        },
    },
    'obhod-glushilok-i.json': {
        'name': '🇷🇺 Обход глушилок I',
        'config': lambda: {
            "dns": {
                "tag": "dns-in",
                "servers": ["8.8.8.8", "9.9.9.9"],
                "queryStrategy": "UseIPv4",
            },
            "log": {"loglevel": "warning"},
            "routing": {
                "rules": [
                    {
                        "type": "field",
                        "protocol": ["bittorrent"],
                        "outboundTag": "direct",
                    },
                    {
                        "type": "field",
                        "domain": [
                            "domain:bps-sberbank.by",
                            "domain:sber-bank.by",
                            "domain:sber.ru",
                            "domain:sberbank.com",
                            "domain:sberbank.ru",
                            "domain:sbrf.ru",
                        ],
                        "outboundTag": "proxy",
                    },
                    {
                        "type": "field",
                        "domain": [
                            "domain:tbank.ru",
                            "domain:t-bank-app.ru",
                            "domain:tinkoff.ru",
                            "domain:tcsbank.ru",
                            "domain:rosbank.ru",
                            "domain:t-bank.by",
                            "domain:tbank-online.com",
                            "domain:cdn-tinkoff.ru",
                            "domain:my-tbank.ru",
                        ],
                        "outboundTag": "proxy",
                    },
                    {
                        "type": "field",
                        "domain": [
                            "domain:mtalk.google.com",
                            "domain:push.apple.com",
                            "domain:api.push.apple.com",
                            "domain:push-apple.com.akadns.net",
                            "domain:courier.push.apple.com",
                            "domain:mangabuff.ru",
                            "domain:yandex.com",
                            "domain:yandex.net",
                            "domain:mail.ru",
                            "domain:vk.com",
                            "domain:vkusvill.ru",
                            "domain:ozon.ru",
                            "domain:wildberries.ru",
                            "domain:sberbank.ru",
                            "domain:tinkoff.ru",
                            "domain:gosuslugi.ru",
                            "domain:nalog.gov.ru",
                            "domain:mos.ru",
                            "domain:2gis.com",
                            "domain:2gis.ru",
                        ],
                        "outboundTag": "direct",
                    },
                    {
                        "ip": ["17.0.0.0/8"],
                        "type": "field",
                        "outboundTag": "direct",
                    },
                    {
                        "type": "field",
                        "domain": [
                            "domain:2ip.ru",
                            "domain:2ip.io",
                            "habr.com",
                            "4pda.to",
                            "4pda.ru",
                            "kemono.su",
                            "jut.su",
                            "kara.su",
                            "theins.ru",
                            "tvrain.ru",
                            "echo.msk.ru",
                            "the-village.ru",
                            "snob.ru",
                            "novayagazeta.ru",
                            "moscowtimes.ru",
                        ],
                        "outboundTag": "proxy",
                    },
                    {
                        "type": "field",
                        "domain": ["geosite:private", "geosite:category-ru"],
                        "outboundTag": "direct",
                    },
                    {
                        "ip": ["geoip:ru", "geoip:private"],
                        "type": "field",
                        "outboundTag": "direct",
                    },
                ],
                "domainStrategy": "IPIfNonMatch",
            },
            "inbounds": [
                {
                    "tag": "socks",
                    "port": 10808,
                    "listen": "127.0.0.1",
                    "protocol": "socks",
                    "settings": {"udp": True, "auth": "noauth"},
                    "sniffing": {
                        "enabled": True,
                        "destOverride": ["http", "tls", "quic"],
                    },
                },
                {
                    "tag": "http",
                    "port": 10809,
                    "listen": "127.0.0.1",
                    "protocol": "http",
                    "settings": {"allowTransparent": False},
                    "sniffing": {
                        "enabled": True,
                        "destOverride": ["http", "tls", "quic"],
                    },
                },
            ],
            "outbounds": [
                {
                    "tag": "proxy",
                    "protocol": "vless",
                    "settings": {
                        "vnext": [
                            {
                                "address": "51.250.18.25",
                                "port": 443,
                                "users": [
                                    {
                                        "id": "0145aa69-a27d-4126-bb14-90dcefc8cc28",
                                        "encryption": "none",
                                        "flow": "xtls-rprx-vision",
                                    }
                                ],
                            }
                        ]
                    },
                    "streamSettings": {
                        "network": "tcp",
                        "tcpSettings": {},
                        "security": "reality",
                        "realitySettings": {
                            "serverName": "ads.x5.ru",
                            "publicKey": "oqRus6Z_Q1jqJaTEPu7ENbRL0-XKOw54K0jwCCGLtEk",
                            "shortId": "5d8e1a9c4f72b3",
                            "fingerprint": "chrome",
                        },
                    },
                },
                {"tag": "direct", "protocol": "freedom"},
                {"tag": "block", "protocol": "blackhole"},
            ],
            "remarks": "🇷🇺 Обход глушилок I",
        },
    },
}


def get_bypass_config(filename):
    config_meta = BYPASS_CONFIGS.get(filename)
    if not config_meta:
        return None
    return config_meta['config']()


def get_external_config(filename):
    safe_filename = Path(filename).name
    if safe_filename != filename or not safe_filename.endswith('.json'):
        return None

    file_path = None
    for config_dir in CONFIG_DIRS:
        candidate = config_dir / safe_filename
        if candidate.is_file():
            file_path = candidate
            break
    if not file_path:
        return None

    try:
        with file_path.open('r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def get_config(filename):
    entry = get_config_entry(filename)
    if not entry:
        return None
    return entry['content']


def get_config_url(token, filename):
    return f"{SUBSCRIPTION_BASE_URL}/config/{token}/{filename}"


def get_raw_subscription_url(token):
    return f"{SUBSCRIPTION_BASE_URL}/sub/{token}"


def get_xray_subscription_url(token):
    return get_raw_subscription_url(token)


def normalize_config_name(name, fallback_name):
    value = (name or fallback_name or 'VPN').strip()
    return value or fallback_name or 'VPN'


def normalize_config(config, display_name):
    normalized = copy.deepcopy(config)
    normalized['remarks'] = display_name

    meta = normalized.get('meta')
    if not isinstance(meta, dict):
        meta = {}
    meta.setdefault('serverDescription', display_name)
    normalized['meta'] = meta

    outbounds = normalized.get('outbounds')
    if not isinstance(outbounds, list) or not outbounds:
        return normalized

    primary_outbound = None
    for outbound in outbounds:
        if not isinstance(outbound, dict):
            continue
        outbound_tag = outbound.get('tag')
        if outbound_tag not in ('direct', 'block'):
            primary_outbound = outbound
            break

    if not primary_outbound:
        return normalized

    old_tag = primary_outbound.get('tag') or 'proxy'
    new_tag = display_name
    primary_outbound['tag'] = new_tag

    routing = normalized.get('routing')
    if isinstance(routing, dict):
        rules = routing.get('rules')
        if isinstance(rules, list):
            for rule in rules:
                if isinstance(rule, dict) and rule.get('outboundTag') == old_tag:
                    rule['outboundTag'] = new_tag

    return normalized


def get_config_entry(filename):
    config = get_bypass_config(filename)
    if config:
        display_name = normalize_config_name(BYPASS_CONFIGS[filename]['name'], Path(filename).stem)
        return {
            'name': display_name,
            'filename': filename,
            'content': normalize_config(config, display_name),
        }

    external_config = get_external_config(filename)
    if not external_config:
        return None

    display_name = normalize_config_name(external_config.get('remarks'), Path(filename).stem)
    return {
        'name': display_name,
        'filename': Path(filename).name,
        'content': normalize_config(external_config, display_name),
    }


def get_external_configs():
    configs = []
    seen_filenames = set()
    for config_dir in CONFIG_DIRS:
        if not config_dir.is_dir():
            continue
        for file_path in sorted(config_dir.glob('*.json'), key=lambda item: item.name.lower()):
            if file_path.name in seen_filenames:
                continue
            seen_filenames.add(file_path.name)
            entry = get_config_entry(file_path.name)
            if not entry:
                continue
            configs.append(entry)
    return configs


def get_subscription_configs():
    return [
        get_config_entry(filename)
        for filename in INTERNAL_CONFIG_FILENAMES
        if filename in BYPASS_CONFIGS
    ] + get_external_configs()


def render_subscription_body(vless_links):
    return '\n'.join(vless_links)


def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def generate_vless_link(uuid, server_key, server_name, short_id=VPS2_SHORT_ID):
    server = SERVERS.get(server_key, SERVERS['estonia'])
    host = server['host']
    port = server['port']
    short_id = server.get('short_id') or short_id
    server_name_sni = server.get('server_name', 'www.google.com')
    if port == 443:
        addr = host
    else:
        addr = f"{host}:{port}"
    return (
        f"vless://{uuid}@{addr}?"
        f"flow=xtls-rprx-vision&encryption=none&security=reality&"
        f"sni={server_name_sni}&fp=chrome&pbk={server['public_key']}&"
        f"sid={short_id}&type=tcp&headerType=none#"
        f"{server['flag']} {server_name}"
    )


def convert_json_config_to_vless(config_content, user_uuid, config_name=None):
    """Convert Xray JSON config to vless:// link using user's UUID."""
    try:
        if isinstance(config_content, str):
            config = json.loads(config_content)
        else:
            config = config_content

        # Find the proxy outbound
        outbounds = config.get('outbounds', [])
        proxy_outbound = None
        for outbound in outbounds:
            if outbound.get('tag') == 'proxy' and outbound.get('protocol') == 'vless':
                proxy_outbound = outbound
                break

        if not proxy_outbound:
            return None

        settings = proxy_outbound.get('settings', {})
        vnext = settings.get('vnext', [])
        if not vnext:
            return None

        server = vnext[0]
        # Use USER's UUID from subscription, not the hardcoded one from config
        address = server.get('address', '')
        port = server.get('port', 443)

        stream_settings = proxy_outbound.get('streamSettings', {})
        security = stream_settings.get('security', 'reality')
        reality_settings = stream_settings.get('realitySettings', {})

        public_key = reality_settings.get('publicKey', '')
        short_id = reality_settings.get('shortId', '')
        server_name = reality_settings.get('serverName', 'www.google.com')
        fingerprint = reality_settings.get('fingerprint', 'chrome')
        flow = server.get('users', [{}])[0].get('flow', 'xtls-rprx-vision')

        # Get remarks from config or use config_name
        remarks = config.get('remarks', config_name or 'Config')

        # Build vless link with USER's UUID
        if port == 443:
            addr = address
        else:
            addr = f"{address}:{port}"

        vless_link = (
            f"vless://{user_uuid}@{addr}?"
            f"flow={flow}&encryption=none&security={security}&"
            f"sni={server_name}&fp={fingerprint}&pbk={public_key}&"
            f"sid={short_id}&type=tcp&headerType=none#"
            f"{quote(remarks)}"
        )
        return vless_link
    except Exception:
        return None


def get_config_vless_links(user_uuid):
    """Get vless:// links from all JSON config files using user's UUID."""
    links = []
    for config in get_subscription_configs():
        vless_link = convert_json_config_to_vless(config['content'], user_uuid, config['name'])
        if vless_link:
            links.append(vless_link)

    # Also check external configs from кфгшки folder
    for config_dir in CONFIG_DIRS:
        if not config_dir.is_dir():
            continue
        for file_path in sorted(config_dir.glob('*.json'), key=lambda item: item.name.lower()):
            if file_path.name in INTERNAL_CONFIG_FILENAMES:
                continue
            try:
                content = file_path.read_text(encoding='utf-8')
                config_data = json.loads(content)
                name = config_data.get('remarks', file_path.stem)
                vless_link = convert_json_config_to_vless(config_data, user_uuid, name)
                if vless_link:
                    links.append(vless_link)
            except Exception:
                continue
    return links


def get_subscription_info(user_id):
    conn = get_db()
    try:
        # Get the most recent key for this user
        cursor = conn.execute(
            """SELECT * FROM vpn_keys
               WHERE user_id = ?
               ORDER BY created_at DESC LIMIT 1""",
            (user_id,)
        )
        key = cursor.fetchone()
        if not key:
            return None
        return {'key': dict(key)}
    finally:
        conn.close()


def build_subscription_headers(expires_at=None, profile_url=None, hide_settings=False):
    headers = {
        'content-disposition': 'attachment; filename="subscription.txt"',
        'profile-title': VPN_NAME,
    }
    if profile_url:
        headers['profile-web-page-url'] = profile_url
    if hide_settings:
        headers['hide-settings'] = '1'
    if expires_at:
        try:
            expiry = datetime.fromisoformat(str(expires_at).replace('Z', '+00:00').replace('+00:00', ''))
            headers['Subscription-Userinfo'] = f'upload=0; download=0; total=0; expire={int(expiry.timestamp())}'
        except Exception:
            pass
    return headers


def fetch_happ_crypto_link(raw_url):
    payload = json.dumps({'url': raw_url}).encode('utf-8')
    request = Request(
        'https://crypto.happ.su/api-v2.php',
        data=payload,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urlopen(request, timeout=4) as response:
            body = response.read().decode('utf-8', errors='replace').strip()
    except Exception:
        return None
    return body if body.startswith('happ://crypt') else None


def build_copy_button(label, value, css_class='btn'):
    escaped_value = html.escape(value).replace('\\', '\\\\').replace("'", "\\'")
    return f'<button class="{css_class}" type="button" onclick="copyText(\'{escaped_value}\')">{html.escape(label)}</button>'


def build_link_button(label, href, css_class='btn'):
    return f'<a class="{css_class}" href="{html.escape(href, quote=True)}">{html.escape(label)}</a>'


def build_app_links_page(token):
    subscription_url = get_raw_subscription_url(token)
    app_name = quote(VPN_NAME)
    encoded_subscription_url = quote(subscription_url, safe='')
    encoded_shadowrocket_url = base64.b64encode(subscription_url.encode('utf-8')).decode('ascii')
    happ_crypto_link = fetch_happ_crypto_link(subscription_url)
    # Надёжный импорт в Happ: основной способ — «крипто»-ссылка happ://crypt…
    # (если сервис доступен), запасной — стандартный deeplink happ://add/<base64>,
    # который работает без внешнего сервиса. Плюс всегда есть кнопка «Скопировать».
    happ_b64 = base64.b64encode(subscription_url.encode('utf-8')).decode('ascii')
    happ_open_link = happ_crypto_link or f"happ://add/{happ_b64}"
    happ_primary_action = build_link_button('Открыть в Happ', happ_open_link, 'btn primary')

    android_apps = [
        {
            'title': 'Happ',
            'badge': 'Рекомендуем',
            'subtitle': 'Самый простой способ: нажмите «Открыть в Happ» — подписка добавится сама. Нет приложения — сначала «Установить».',
            'actions': [
                happ_primary_action,
                build_copy_button('Скопировать ссылку', subscription_url),
                build_link_button('Установить', 'https://play.google.com/store/apps/details?id=com.happproxy'),
            ],
        },
        {
            'title': 'Hiddify',
            'subtitle': 'Импорт подписки по кнопке «Открыть».',
            'actions': [
                build_link_button('Открыть', f'hiddify://import/{encoded_subscription_url}#{app_name}', 'btn primary'),
                build_link_button('Установить', 'https://play.google.com/store/apps/details?id=app.hiddify.com'),
            ],
        },
        {
            'title': 'v2rayNG',
            'subtitle': 'Нажмите «Скопировать», затем в приложении: + → Импорт из буфера обмена.',
            'actions': [
                build_copy_button('Скопировать ссылку', subscription_url, 'btn primary'),
                build_link_button('Установить', 'https://play.google.com/store/apps/details?id=com.v2ray.ang'),
            ],
        },
        {
            'title': 'V2Box',
            'subtitle': 'Добавляет подписку в один тап по кнопке «Открыть».',
            'actions': [
                build_link_button('Открыть', f'v2box://install-sub?url={encoded_subscription_url}&name={app_name}', 'btn primary'),
            ],
        },
        {
            'title': 'v2RayTun',
            'subtitle': 'Кнопка «Открыть» импортирует подписку.',
            'actions': [
                build_link_button('Открыть', f'v2raytun://import-sub?url={encoded_subscription_url}', 'btn primary'),
                build_copy_button('Скопировать', subscription_url),
            ],
        },
    ]

    ios_apps = [
        {
            'title': 'Happ',
            'badge': 'Рекомендуем',
            'subtitle': 'Нажмите «Открыть в Happ» — подписка добавится сама. Нет приложения — сначала «Установить».',
            'actions': [
                happ_primary_action,
                build_copy_button('Скопировать ссылку', subscription_url),
                build_link_button('Установить', 'https://apps.apple.com/app/happ-proxy-utility/id6504287215'),
            ],
        },
        {
            'title': 'Shadowrocket',
            'subtitle': 'Импорт подписки по кнопке «Открыть».',
            'actions': [
                build_link_button('Открыть', f'shadowrocket://add/sub://{encoded_shadowrocket_url}?remark={app_name}', 'btn primary'),
            ],
        },
        {
            'title': 'Streisand',
            'subtitle': 'Скопируйте ссылку и выберите «Import from Clipboard» в приложении.',
            'actions': [
                build_copy_button('Скопировать ссылку', subscription_url, 'btn primary'),
            ],
        },
        {
            'title': 'Hiddify',
            'subtitle': 'Прямой импорт подписки по кнопке «Открыть».',
            'actions': [
                build_link_button('Открыть', f'hiddify://import/{encoded_subscription_url}#{app_name}', 'btn primary'),
                build_link_button('Установить', 'https://apps.apple.com/app/hiddify-proxy-vpn/id6596777532'),
            ],
        },
        {
            'title': 'V2Box',
            'subtitle': 'Добавляет подписку по кнопке «Открыть».',
            'actions': [
                build_link_button('Открыть', f'v2box://install-sub?url={encoded_subscription_url}&name={app_name}', 'btn primary'),
            ],
        },
    ]

    desktop_apps = [
        {
            'title': 'Hiddify',
            'badge': 'Рекомендуем',
            'subtitle': 'Windows, macOS и Linux. Нажмите «Открыть» или скопируйте ссылку.',
            'actions': [
                build_link_button('Открыть', f'hiddify://import/{encoded_subscription_url}#{app_name}', 'btn primary'),
                build_copy_button('Скопировать', subscription_url),
            ],
        },
        {
            'title': 'Happ Desktop',
            'subtitle': 'Открывает импорт подписки. Либо добавьте ссылку вручную.',
            'actions': [
                happ_primary_action,
                build_copy_button('Скопировать', subscription_url),
            ],
        },
        {
            'title': 'NekoRay',
            'subtitle': 'Скопируйте ссылку и добавьте её как Subscription.',
            'actions': [
                build_copy_button('Скопировать ссылку', subscription_url, 'btn primary'),
                build_link_button('Скачать', 'https://github.com/MatsuriDayo/nekoray/releases'),
            ],
        },
        {
            'title': 'v2rayN',
            'subtitle': 'Скопируйте ссылку и добавьте её как Subscription.',
            'actions': [
                build_copy_button('Скопировать ссылку', subscription_url, 'btn primary'),
                build_link_button('Скачать', 'https://github.com/2dust/v2rayN/releases'),
            ],
        },
    ]

    icon_shield = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 19 6v5c0 4.4-3 7.6-7 9-4-1.4-7-4.6-7-9V6z"/></svg>'
    icon_mobile = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="7" y="2.5" width="10" height="19" rx="2.5"/><path d="M10.5 18.5h3"/></svg>'
    icon_laptop = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="16" height="11" rx="2"/><path d="M2 19h20"/></svg>'

    def render_platform_section(apps, pf_id):
        cards = []
        for app in apps:
            badge = f'<span class="rec">{html.escape(app["badge"])}</span>' if app.get("badge") else ""
            rec_cls = " rec-card" if app.get("badge") else ""
            cards.append(
                f"""<div class="app-card{rec_cls}">
  <div class="app-head"><span class="app-title">{html.escape(app['title'])}</span>{badge}</div>
  <div class="app-subtitle">{html.escape(app['subtitle'])}</div>
  <div class="actions">{''.join(app['actions'])}</div>
</div>"""
            )
        return f"""<section class="platform" data-pf="{pf_id}">
  <div class="apps">{''.join(cards)}</div>
</section>"""

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <title>Подключение — {html.escape(VPN_NAME)}</title>
  <style>
    :root {{
      --bg:#141a22;--surface:#1b232e;--surface2:#222c39;--border:rgba(255,255,255,.08);
      --text:#e7ecf2;--muted:#8f9bac;--accent:#5c8bbf;--accent-deep:#4a76a6;
      --accent-soft:rgba(92,139,191,.12);--code:#10151c;
    }}
    *{{box-sizing:border-box}}
    body {{
      margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
      background:var(--bg);color:var(--text);line-height:1.5;
      display:flex;justify-content:center;padding:22px 18px 40px;
    }}
    .wrap{{width:100%;max-width:540px}}
    .head{{display:flex;align-items:center;gap:12px;margin-bottom:18px}}
    .logo{{width:44px;height:44px;border-radius:12px;background:var(--accent-deep);
      display:flex;align-items:center;justify-content:center;color:#fff;flex:none}}
    .logo svg{{width:24px;height:24px}}
    .head h1{{font-size:18px;margin:0}}
    .head .sub{{font-size:12px;color:var(--muted);margin-top:2px}}
    .intro{{color:var(--muted);font-size:14px;margin:0 0 18px}}
    .linkcard{{background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:16px;margin-bottom:24px}}
    .label{{font-size:12px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:10px}}
    .mono{{background:var(--code);border:1px solid var(--border);border-radius:11px;padding:12px;
      font-family:ui-monospace,Menlo,monospace;font-size:12px;color:#bcd0e3;word-break:break-all}}
    .tabs{{display:flex;gap:8px;margin-bottom:16px}}
    .tabs button{{flex:1;display:flex;align-items:center;justify-content:center;gap:6px;
      background:var(--surface);border:1px solid var(--border);color:var(--muted);border-radius:11px;
      padding:11px 8px;font:inherit;font-weight:600;font-size:13px;cursor:pointer}}
    .tabs button.active{{background:var(--accent-deep);border-color:var(--accent-deep);color:#fff}}
    .tabs svg{{width:17px;height:17px;flex:none}}
    .platform{{display:none}}
    .platform.active{{display:block}}
    .apps{{display:grid;gap:10px}}
    .app-head{{display:flex;align-items:center;gap:8px;margin-bottom:5px}}
    .rec{{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.4px;color:var(--accent);
      background:var(--accent-soft);border:1px solid rgba(92,139,191,.3);padding:2px 8px;border-radius:999px}}
    .rec-card{{border-color:rgba(92,139,191,.4)}}
    .app-card{{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:14px}}
    .app-title{{font-size:16px;font-weight:700;margin-bottom:4px}}
    .app-subtitle{{color:var(--muted);font-size:13px;margin-bottom:12px}}
    .actions{{display:flex;flex-wrap:wrap;gap:8px}}
    .btn {{
      display:inline-flex;align-items:center;justify-content:center;min-height:46px;
      padding:10px 16px;border-radius:11px;background:var(--surface2);color:var(--text);
      text-decoration:none;border:1px solid var(--border);font-weight:600;font-size:14px;
      cursor:pointer;flex:1;min-width:120px
    }}
    button.btn{{font:inherit}}
    .btn.primary{{background:var(--accent-deep);border-color:var(--accent-deep);color:#fff}}
    .btn:active{{transform:scale(.99)}}
    .copy-row{{margin-top:12px}}
    .copy-row .btn{{width:100%}}
    .note{{font-size:13px;color:var(--muted);margin-top:14px}}
    .toast{{position:fixed;left:50%;bottom:24px;transform:translateX(-50%) translateY(20px);
      background:#252e3b;border:1px solid var(--border);color:var(--text);padding:11px 18px;
      border-radius:12px;font-size:14px;font-weight:600;opacity:0;transition:.3s;pointer-events:none}}
    .toast.show{{opacity:1;transform:translateX(-50%) translateY(0)}}
  </style>
  <script>
    function copyText(value) {{
      function done() {{
        var t = document.getElementById('toast');
        t.textContent = 'Ссылка скопирована — вставьте её в приложении';
        t.classList.add('show');
        setTimeout(function() {{ t.classList.remove('show'); }}, 2400);
      }}
      if (navigator.clipboard && navigator.clipboard.writeText) {{
        navigator.clipboard.writeText(value).then(done).catch(function() {{ prompt('Скопируйте ссылку:', value); }});
      }} else {{
        prompt('Скопируйте ссылку:', value);
      }}
    }}
  </script>
</head>
<body>
  <div class="wrap">
    <div class="head">
      <div class="logo">{icon_shield}</div>
      <div><h1>{html.escape(VPN_NAME)}</h1><div class="sub">Подключение устройства</div></div>
    </div>
    <p class="intro">Выберите своё приложение — где поддерживается, подписка добавится в один тап. Если кнопка «Открыть» не сработала, нажмите «Скопировать» и вставьте ссылку в приложении вручную.</p>

    <div class="linkcard">
      <div class="label">Ваша ссылка подписки</div>
      <div class="mono">{html.escape(subscription_url)}</div>
      <div class="copy-row">
        <button class="btn primary" type="button" onclick="copyText('{html.escape(subscription_url)}')">Скопировать ссылку</button>
      </div>
    </div>

    <div class="tabs">
      <button type="button" data-pf="android" onclick="showPf('android')">{icon_mobile}Android</button>
      <button type="button" data-pf="ios" onclick="showPf('ios')">{icon_mobile}iPhone</button>
      <button type="button" data-pf="desktop" onclick="showPf('desktop')">{icon_laptop}ПК</button>
    </div>
    {render_platform_section(android_apps, 'android')}
    {render_platform_section(ios_apps, 'ios')}
    {render_platform_section(desktop_apps, 'desktop')}

    <p class="note">Если кнопка «Открыть» не сработала — установите приложение, вернитесь сюда и нажмите снова. Либо «Скопировать» и вставьте ссылку в приложении вручную.</p>
    <div id="toast" class="toast"></div>
  </div>
  <script>
    function showPf(id) {{
      var ss = document.querySelectorAll('.platform');
      for (var i = 0; i < ss.length; i++) ss[i].classList.toggle('active', ss[i].getAttribute('data-pf') === id);
      var bs = document.querySelectorAll('.tabs button');
      for (var j = 0; j < bs.length; j++) bs[j].classList.toggle('active', bs[j].getAttribute('data-pf') === id);
    }}
    (function () {{
      var ua = navigator.userAgent || '';
      var pf = 'android';
      if (/iPhone|iPad|iPod/.test(ua)) pf = 'ios';
      else if (/Windows|Macintosh|Mac OS|Linux/.test(ua) && !/Android/.test(ua)) pf = 'desktop';
      showPf(pf);
    }})();
  </script>
</body>
</html>"""


class SubHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _sec_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Robots-Tag', 'noindex, nofollow')
        self.send_header('Server', 'aeroproject')

    def _send_json(self, status, data):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self._sec_headers()
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def _send_text(self, status, text, headers=None):
        self.send_response(status)
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self._sec_headers()
        if headers:
            for k, v in headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(text.encode())

    def _send_html(self, status, html):
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self._sec_headers()
        self.end_headers()
        self.wfile.write(html.encode())

    def _redirect(self, location):
        self.send_response(302)
        self.send_header('Location', location)
        self.end_headers()

    def _is_browser_request(self):
        accept = (self.headers.get('Accept') or '').lower()
        user_agent = (self.headers.get('User-Agent') or '').lower()
        if 'text/html' in accept:
            return True
        if self.headers.get('Sec-Fetch-Mode'):
            return True
        browser_markers = ('mozilla/', 'applewebkit/', 'chrome/', 'safari/', 'telegram')
        client_markers = ('happ', 'okhttp', 'cfnetwork', 'go-http-client', 'curl', 'wget', 'python', 'v2ray', 'xray', 'sing-box', 'clash')
        return any(marker in user_agent for marker in browser_markers) and not any(marker in user_agent for marker in client_markers)

    def do_HEAD(self):
        if not _rl_allow(_rl_client_ip(self)):
            self.send_response(429)
            self.end_headers()
            return
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith('/sub/'):
            token = path.split('/sub/')[1]
            user_id = decrypt_token(token)
            if not user_id:
                self.send_response(400)
                self.send_header('Content-Type', 'text/plain; charset=utf-8')
                self.end_headers()
                return

            sub_info = get_subscription_info(user_id)
            if not sub_info:
                self.send_response(404)
                self.send_header('Content-Type', 'text/plain; charset=utf-8')
                self.end_headers()
                return

            expires_at = sub_info['key']['expires_at']
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            for header_name, header_value in build_subscription_headers(expires_at=expires_at).items():
                self.send_header(header_name, header_value)
            self.end_headers()
            return

        if path.startswith('/xray-sub/'):
            token = path.split('/xray-sub/')[1]
            self.send_response(302)
            self.send_header('Location', f'/sub/{token}')
            self.end_headers()
            return

        if path.startswith('/api/sub/'):
            token = path.split('/api/sub/')[1]
            user_id = decrypt_token(token)
            if not user_id:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                return

            sub_info = get_subscription_info(user_id)
            if not sub_info:
                self.send_response(404)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                return

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            return

        if path.startswith('/config/'):
            remainder = path.split('/config/')[1]
            parts = remainder.split('/', 1)
            token = parts[0]
            filename = parts[1] if len(parts) > 1 and parts[1] else 'obhod-glushilok.json'
            user_id = decrypt_token(token)
            if not user_id:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                return

            sub_info = get_subscription_info(user_id)
            if not sub_info:
                self.send_response(404)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                return

            if not get_config(filename):
                self.send_response(404)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                return

            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            return

        if path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.end_headers()
            return

        self.send_response(404)
        self.end_headers()

    def do_GET(self):
        if not _rl_allow(_rl_client_ip(self)):
            self._send_text(429, "Too many requests")
            return
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith('/sub/'):
            token = path.split('/sub/')[1]
            user_id = decrypt_token(token)
            if not user_id:
                self._send_text(400, "Invalid token")
                return

            sub_info = get_subscription_info(user_id)
            if not sub_info:
                self._send_text(404, "No active subscription")
                return

            uuid = sub_info['key']['uuid']
            expires_at_str = sub_info['key']['expires_at']
            is_active = sub_info['key'].get('is_active', 1)
            
            # Check if expired or inactive
            is_expired = False
            expires_at = None
            if expires_at_str:
                try:
                    expires_at = datetime.fromisoformat(str(expires_at_str).replace('Z', '+00:00').replace('+00:00', ''))
                    if expires_at < datetime.now():
                        is_expired = True
                except Exception:
                    pass

            if is_expired or not is_active:
                content = "Подписка закончилась, купить VPN: @AeroProjectVPN"
                self._send_text(200, content, build_subscription_headers(expires_at=expires_at))
                return

            links = []
            for server_key, server in SERVERS.items():
                links.append(generate_vless_link(uuid, server_key, server['name']))

            # Add VLESS links from JSON config files
            config_vless_links = get_config_vless_links(uuid)
            links.extend(config_vless_links)

            content = render_subscription_body(links)
            extra_headers = build_subscription_headers(expires_at=expires_at)
            self._send_text(200, content, extra_headers)
            return

        if path.startswith('/xray-sub/'):
            token = path.split('/xray-sub/')[1]
            self._redirect(f'/sub/{token}')
            return

        if path.startswith('/api/sub/'):
            token = path.split('/api/sub/')[1]
            user_id = decrypt_token(token)
            if not user_id:
                self._send_json(400, {'error': 'Invalid token'})
                return

            sub_info = get_subscription_info(user_id)
            if not sub_info:
                self._send_json(404, {'error': 'No active subscription'})
                return

            uuid = sub_info['key']['uuid']
            expires_at = sub_info['key']['expires_at']

            servers = []
            for server_key, server in SERVERS.items():
                link = generate_vless_link(uuid, server_key, server['name'])
                servers.append({'name': f"{server['flag']} {server['name']}", 'type': 'vless', 'link': link})

            # Add VLESS links from config files
            for vless_link in get_config_vless_links(uuid):
                # Extract name from link (after #)
                name = vless_link.split('#')[-1] if '#' in vless_link else 'Config'
                name = name.replace('%20', ' ').replace('%', '')  # Basic URL decode
                servers.append({'name': name, 'type': 'vless', 'link': vless_link})

            days_remaining = 9999
            if expires_at:
                try:
                    expiry = datetime.fromisoformat(str(expires_at).replace('Z', '+00:00').replace('+00:00', ''))
                    days_remaining = (expiry - datetime.now()).days
                except Exception:
                    pass

            payload = {
                'vpn_name': VPN_NAME,
                'expires_at': expires_at,
                'days_remaining': days_remaining,
                'servers': servers,
                'total_servers': len(servers),
                'configs': [
                    {
                        'name': config['name'],
                        'type': 'xray-json',
                        'config': config['content'],
                    }
                    for config in get_subscription_configs()
                ],
            }

            self._send_json(200, payload)
            return

        if path.startswith('/config/'):
            remainder = path.split('/config/')[1]
            parts = remainder.split('/', 1)
            token = parts[0]
            filename = parts[1] if len(parts) > 1 and parts[1] else 'obhod-glushilok.json'
            user_id = decrypt_token(token)
            if not user_id:
                self._send_json(400, {'error': 'Invalid token'})
                return

            sub_info = get_subscription_info(user_id)
            if not sub_info:
                self._send_json(404, {'error': 'No active subscription'})
                return

            config = get_config(filename)
            if not config:
                self._send_json(404, {'error': 'Config not found'})
                return

            self._send_json(200, config)
            return

        if path.startswith('/app/'):
            token = path.split('/app/')[1]
            user_id = decrypt_token(token)
            if not user_id:
                self._send_text(400, "Invalid token")
                return
            self._send_html(200, build_app_links_page(token))
            return

        if path == '/':
            example_token = encrypt_user_id(123456789)
            text = (
                f"{VPN_NAME} Subscription Service\n\n"
                f"Subscription URL:\n"
                f"https://vpn.aeroproject.fun/sub/TOKEN\n\n"
                f"Example token:\n"
                f"{example_token}\n"
            )
            self._send_text(200, text)
            return

        self.send_response(404)
        self.end_headers()


if __name__ == '__main__':
    server = HTTPServer(('0.0.0.0', 9091), SubHandler)
    print("Subscription API running on port 9091")
    server.serve_forever()
