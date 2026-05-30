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
    happ_primary_action = (
        build_link_button('Открыть', happ_crypto_link, 'btn primary')
        if happ_crypto_link else
        build_copy_button('Скопировать ссылку', subscription_url, 'btn primary')
    )

    android_apps = [
        {
            'title': 'Happ',
            'subtitle': 'Открывает импорт подписки. Если доступно, используется скрытая `happ://crypt...` ссылка.',
            'actions': [
                happ_primary_action,
                build_link_button('Сайт', 'https://happ.info'),
            ],
        },
        {
            'title': 'Hiddify',
            'subtitle': 'Импортирует подписку напрямую через deeplink.',
            'actions': [
                build_link_button('Открыть', f'hiddify://import/{encoded_subscription_url}#{app_name}', 'btn primary'),
                build_link_button('Сайт', 'https://hiddify.com/app/'),
            ],
        },
        {
            'title': 'V2Box',
            'subtitle': 'Добавляет подписку по URL в один тап.',
            'actions': [
                build_link_button('Открыть', f'v2box://install-sub?url={encoded_subscription_url}&name={app_name}', 'btn primary'),
            ],
        },
        {
            'title': 'v2rayNG',
            'subtitle': 'Копирует ссылку. Дальше вставь её в `Subscription group setting` внутри приложения.',
            'actions': [
                build_copy_button('Скопировать ссылку', subscription_url, 'btn primary'),
                build_link_button('Скачать', 'https://github.com/2dust/v2rayNG/releases'),
            ],
        },
        {
            'title': 'v2rayTun',
            'subtitle': 'Если приложение поддерживает deeplink, подписка импортируется сразу.',
            'actions': [
                build_link_button('Открыть', f'v2raytun://import-sub?url={encoded_subscription_url}', 'btn primary'),
                build_copy_button('Скопировать ссылку', subscription_url),
            ],
        },
        {
            'title': 'NekoBox / NekoRay Android',
            'subtitle': 'Надёжный вариант: скопировать ссылку и импортировать из URL/буфера внутри приложения.',
            'actions': [
                build_copy_button('Скопировать ссылку', subscription_url, 'btn primary'),
            ],
        },
    ]

    ios_apps = [
        {
            'title': 'Happ',
            'subtitle': 'Открывает скрытый импорт подписки, если сервис шифрования доступен.',
            'actions': [
                happ_primary_action,
                build_link_button('Сайт', 'https://happ.info'),
            ],
        },
        {
            'title': 'Shadowrocket',
            'subtitle': 'Импортирует подписку по deeplink.',
            'actions': [
                build_link_button('Открыть', f'shadowrocket://add/sub://{encoded_shadowrocket_url}?remark={app_name}', 'btn primary'),
            ],
        },
        {
            'title': 'Hiddify',
            'subtitle': 'Прямой импорт подписки.',
            'actions': [
                build_link_button('Открыть', f'hiddify://import/{encoded_subscription_url}#{app_name}', 'btn primary'),
                build_link_button('Сайт', 'https://hiddify.com/app/'),
            ],
        },
        {
            'title': 'V2Box',
            'subtitle': 'Добавляет подписку по deeplink.',
            'actions': [
                build_link_button('Открыть', f'v2box://install-sub?url={encoded_subscription_url}&name={app_name}', 'btn primary'),
            ],
        },
        {
            'title': 'Streisand',
            'subtitle': 'Скопируй ссылку и выбери `Import from Clipboard` в приложении.',
            'actions': [
                build_copy_button('Скопировать ссылку', subscription_url, 'btn primary'),
            ],
        },
    ]

    desktop_apps = [
        {
            'title': 'Hiddify Desktop',
            'subtitle': 'На ПК deeplink может открыться сразу. Если нет, просто скопируй ссылку.',
            'actions': [
                build_link_button('Открыть', f'hiddify://import/{encoded_subscription_url}#{app_name}', 'btn primary'),
                build_copy_button('Скопировать ссылку', subscription_url),
            ],
        },
        {
            'title': 'Happ Desktop',
            'subtitle': 'Использует скрытую ссылку, либо ручное добавление подписки.',
            'actions': [
                happ_primary_action,
                build_copy_button('Скопировать ссылку', subscription_url),
            ],
        },
        {
            'title': 'NekoRay',
            'subtitle': 'Вставь ссылку в `Server -> Subscription Settings` или в группу Subscription.',
            'actions': [
                build_copy_button('Скопировать ссылку', subscription_url, 'btn primary'),
                build_link_button('Скачать', 'https://github.com/MatsuriDayo/nekoray/releases'),
            ],
        },
        {
            'title': 'v2rayN',
            'subtitle': 'Скопируй ссылку и добавь её как Subscription в приложении.',
            'actions': [
                build_copy_button('Скопировать ссылку', subscription_url, 'btn primary'),
                build_link_button('Скачать', 'https://github.com/2dust/v2rayN/releases'),
            ],
        },
        {
            'title': 'Clash / Clash Verge / Clash Meta GUI',
            'subtitle': 'Если нужен обычный URL подписки, используй кнопку ниже с обычной ссылкой.',
            'actions': [
                build_copy_button('Скопировать обычную ссылку', raw_subscription_url, 'btn primary'),
            ],
        },
    ]

    def render_platform_section(title, apps):
        cards = []
        for app in apps:
            cards.append(
                f"""<div class="app-card">
  <div class="app-title">{html.escape(app['title'])}</div>
  <div class="app-subtitle">{html.escape(app['subtitle'])}</div>
  <div class="actions">{''.join(app['actions'])}</div>
</div>"""
            )
        return f"""<section class="platform">
  <h2>{html.escape(title)}</h2>
  <div class="apps">{''.join(cards)}</div>
</section>"""

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Добавить подписку</title>
  <style>
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #0b1220;
      color: #f3f4f6;
      display: flex;
      justify-content: center;
      padding: 24px;
    }}
    .card {{
      width: 100%;
      max-width: 520px;
      background: #111827;
      border: 1px solid #1f2937;
      border-radius: 20px;
      padding: 24px;
      box-shadow: 0 20px 60px rgba(0, 0, 0, 0.35);
    }}
    h1 {{
      margin: 0 0 12px;
      font-size: 28px;
    }}
    h2 {{
      margin: 22px 0 12px;
      font-size: 20px;
    }}
    p {{
      margin: 0 0 18px;
      color: #cbd5e1;
      line-height: 1.5;
    }}
    .apps {{
      display: grid;
      grid-template-columns: 1fr;
      gap: 12px;
    }}
    .app-card {{
      background: #0f172a;
      border: 1px solid #1e293b;
      border-radius: 16px;
      padding: 14px;
    }}
    .app-title {{
      font-size: 18px;
      font-weight: 700;
      margin-bottom: 6px;
    }}
    .app-subtitle {{
      color: #cbd5e1;
      font-size: 14px;
      line-height: 1.45;
      margin-bottom: 12px;
    }}
    .actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }}
    .btn {{
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 52px;
      padding: 12px 14px;
      border-radius: 14px;
      background: #1f2937;
      color: #f9fafb;
      text-decoration: none;
      border: 1px solid #374151;
      font-weight: 600;
      cursor: pointer;
    }}
    button.btn {{
      font: inherit;
    }}
    .primary {{
      background: #2563eb;
      border-color: #2563eb;
    }}
    .secondary {{
      margin-top: 10px;
      background: #0f172a;
    }}
    .note {{
      font-size: 14px;
      color: #94a3b8;
      margin-top: 8px;
    }}
    .mono {{
      word-break: break-all;
      background: #0f172a;
      border: 1px solid #1e293b;
      border-radius: 12px;
      padding: 12px;
      font-size: 13px;
      color: #cbd5e1;
      margin-top: 12px;
    }}
  </style>
  <script>
    function copyText(value) {{
      if (navigator.clipboard && navigator.clipboard.writeText) {{
        navigator.clipboard.writeText(value).then(function() {{
          alert('Ссылка скопирована. Открой Happ и вставь ее как подписку.');
        }});
        return;
      }}
      alert(value);
    }}
  </script>
</head>
<body>
  <div class="card">
    <h1>Добавить подписку</h1>
    <p>Выбери приложение под свою платформу. Где deeplink поддерживается, импорт откроется сразу. Где его нет, кнопка скопирует ссылку для вставки внутри приложения.</p>
    {render_platform_section('Android', android_apps)}
    {render_platform_section('iPhone / iPad', ios_apps)}
    {render_platform_section('ПК: Windows / macOS / Linux', desktop_apps)}
    <a class="btn secondary" href="{html.escape(subscription_url, quote=True)}">Открыть прямую подписку</a>
    <button class="btn secondary" type="button" onclick="copyText('{html.escape(subscription_url)}')">Скопировать подписку</button>
    <p class="note">Для Happ кнопка использует скрытую ссылку, если сервис шифрования доступен. Иначе копируется прямая ссылка подписки.</p>
    <div class="mono">{html.escape(subscription_url)}</div>
  </div>
</body>
</html>"""


class SubHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _send_json(self, status, data):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def _send_text(self, status, text, headers=None):
        self.send_response(status)
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        if headers:
            for k, v in headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(text.encode())

    def _send_html(self, status, html):
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
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
