"""
services.py — общая бизнес-логика для Mini App (webapp_api.py) и бота (bot.py).

Главное здесь — валидация Telegram WebApp initData (без неё нельзя доверять
user_id с клиента). Плюс выдача ключей, сборка профиля и тонкие хелперы Bot API
поверх stdlib (urllib) — чтобы не тащить лишние зависимости.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from typing import Any, Optional

from config import (
    ADMIN_IDS,
    BOT_TOKEN,
    BOT_USERNAME,
    CARD_RU,
    CARD_UA,
    CHANNEL_ID,
    CHANNEL_REQUIRED,
    CHANNEL_USERNAME,
    DEVICE_LIMIT_DEFAULT,
    DEVICE_PACK_PRICE,
    DEVICE_PACK_SIZE,
    PRICES,
    SUBSCRIPTION_BASE_URL,
    TRIAL_DAYS,
    VPN_NAME,
)
from token_crypto import encrypt_user_id

PLAN_DAYS = {
    "1_month": 30,
    "3_months": 90,
    "6_months": 180,
    "1_year": 365,
}
PLAN_TITLE = {
    "1_month": "1 месяц",
    "3_months": "3 месяца",
    "6_months": "6 месяцев",
    "1_year": "1 год",
}

# Порядок и акценты тарифов в Mini App.
PLAN_ORDER = ("1_month", "3_months", "6_months", "1_year")
PLAN_BADGE = {
    "3_months": "Старт",
    "6_months": "Хит",
    "1_year": "Выгодно",
}

# Идентификатор «товара» докупки устройств в заказах.
DEVICES_PLAN = "devices_10"
PLAN_TITLE[DEVICES_PLAN] = f"+{DEVICE_PACK_SIZE} устройств"


def is_devices_plan(plan: Optional[str]) -> bool:
    return bool(plan) and str(plan).startswith("devices")


# ==================== БЕЗОПАСНОСТЬ: ВАЛИДАЦИЯ initData ====================

def validate_init_data(init_data: str, max_age_seconds: int = 86400) -> Optional[dict]:
    """Проверить подпись Telegram WebApp initData.

    Возвращает разобранный dict (с распарсенным полем 'user') либо None,
    если подпись неверна или данные просрочены. НИКОГДА не доверяй user_id
    с фронта без этой проверки.
    """
    if not init_data:
        return None
    try:
        parsed = dict(urllib.parse.parse_qsl(init_data, strict_parsing=True, keep_blank_values=True))
    except Exception:
        return None

    received_hash = parsed.pop("hash", None)
    if not received_hash:
        return None

    data_check_string = "\n".join(f"{k}={parsed[k]}" for k in sorted(parsed))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    calc_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(calc_hash, received_hash):
        return None

    # Свежесть (защита от повторного использования старого initData)
    try:
        auth_date = int(parsed.get("auth_date", "0"))
        if max_age_seconds and auth_date and (time.time() - auth_date) > max_age_seconds:
            return None
    except Exception:
        pass

    if "user" in parsed:
        try:
            parsed["user"] = json.loads(parsed["user"])
        except Exception:
            parsed["user"] = None

    return parsed


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# ==================== TELEGRAM BOT API (через stdlib) ====================

def _bot_api(method: str, payload: dict) -> Optional[dict]:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    data = urllib.parse.urlencode(payload).encode()
    try:
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return None


def tg_send_message(chat_id: int, text: str, reply_markup: Optional[dict] = None) -> Optional[dict]:
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }
    if reply_markup is not None:
        payload["reply_markup"] = json.dumps(reply_markup)
    return _bot_api("sendMessage", payload)


def check_channel_membership(user_id: int) -> bool:
    """True, если юзер в канале (или проверка не требуется / недоступна)."""
    if not CHANNEL_REQUIRED:
        return True
    resp = _bot_api("getChatMember", {"chat_id": CHANNEL_ID, "user_id": user_id})
    if not resp or not resp.get("ok"):
        # Не блокируем пользователя из-за сбоя проверки.
        return True
    status = (resp.get("result") or {}).get("status")
    return status in ("member", "administrator", "creator")


# ==================== ДАТЫ / ФОРМАТ ====================

def _parse_dt(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "").replace("+00:00", ""))
    except Exception:
        return None


def get_subscription_url(user_id: int) -> str:
    return f"{SUBSCRIPTION_BASE_URL}/sub/{encrypt_user_id(user_id)}"


def get_referral_link(user_id: int) -> str:
    return f"https://t.me/{BOT_USERNAME}?start=ref_{encrypt_user_id(user_id)}"


# ==================== ВЫДАЧА КЛЮЧА (блокирующее, SSH) ====================

def issue_key(db, user_id: int, days: Optional[int]) -> dict:
    """Создать VLESS-ключ на Эстонии и сохранить в БД. Блокирующая операция (SSH)."""
    from vpn_manager import VPNManager  # локальный импорт: paramiko нужен только тут

    device_limit = db.get_device_limit(user_id)

    vpn = VPNManager()
    key_data = vpn.generate_vpn_key(user_id, days=days, device_limit=device_limit)
    db.add_vpn_key(
        user_id=user_id,
        uuid=key_data["uuid"],
        public_key=key_data["public_key"],
        private_key=key_data["private_key"],
        short_id=key_data["short_id"],
        expires_at=key_data["expires_at"],
        vless_link=key_data["vless_link"],
        server="estonia",
        email=key_data.get("email"),
    )
    return key_data


def extend_or_issue_key(db, user_id: int, days: Optional[int]) -> dict:
    """ПРОДЛИТЬ срок активного ключа на `days` или выдать новый, если ключа нет.

    Это правильная логика оплаты: дни ПРИБАВЛЯЮТСЯ к текущей дате окончания
    (а если ключ уже истёк — считаем от сейчас). Срок обновляется И в БД,
    И на 3x-ui-панели у ТОГО ЖЕ клиента (uuid/email не меняются) — поэтому
    уже импортированная пользователем подписка продолжает работать, просто
    с новой датой. Работает даже если сейчас активен пробный (trial) тариф:
    его остаток сохраняется, а оплаченные дни добавляются сверху.

    days=None трактуется как «бессрочно» (expiry снимается).
    """
    key = db.get_active_key(user_id)
    if not key:
        # Активного ключа нет — выдаём новый обычным путём.
        return issue_key(db, user_id, days)

    key_id = key[0]
    uuid_val = key[2]
    email = key[-1]  # email — последняя колонка vpn_keys
    current_expiry = _parse_dt(key[7])
    now = datetime.now()

    if days:
        # База: текущий срок, если он ещё в будущем (продлеваем), иначе — сейчас.
        base = current_expiry if (current_expiry and current_expiry > now) else now
        new_expiry = base + timedelta(days=days)
    else:
        new_expiry = None  # бессрочно

    device_limit = db.get_device_limit(user_id)

    # 1) Обновляем срок на 3x-ui-панели (тот же клиент: ключ не перевыпускаем).
    try:
        from vpn_manager import VPNManager
        VPNManager().set_key_expiry(uuid_val, email, new_expiry, device_limit)
    except Exception as exc:
        print(f"extend_or_issue_key: panel expiry update failed: {exc}")

    # 2) Обновляем срок в БД.
    db.update_key_expiry(key_id, new_expiry)

    return {
        "uuid": uuid_val,
        "email": email,
        "expires_at": new_expiry,
        "extended": True,
    }


def build_devices_state(db, user_id: int) -> dict:
    """Состояние устройств для Mini App: лимит, занято, цена докупки."""
    limit = db.get_device_limit(user_id)
    email = db.get_active_key_email(user_id)

    used = 0
    online = False
    if email:
        try:
            from vpn_manager import VPNManager
            info = VPNManager().get_connected_devices(email)
            used = info.get("count", 0)
            online = info.get("online", False)
        except Exception:
            pass

    return {
        "limit": limit,
        "used": min(used, limit) if limit else used,
        "online": online,
        "has_key": bool(email),
        "pack_size": DEVICE_PACK_SIZE,
        "pack_price": DEVICE_PACK_PRICE,
        "default": DEVICE_LIMIT_DEFAULT,
    }


def apply_device_limit(db, user_id: int) -> bool:
    """Применить текущий лимит устройств пользователя к его активному ключу в 3x-ui."""
    key = db.get_active_key(user_id)
    if not key:
        return False
    uuid_val = key[2]      # vpn_keys.uuid
    email = key[-1]        # vpn_keys.email (последняя колонка)
    if not email:
        return False
    try:
        from vpn_manager import VPNManager
        return VPNManager().set_device_limit(uuid_val, email, db.get_device_limit(user_id))
    except Exception:
        return False


# ==================== СБОРКА СОСТОЯНИЯ ДЛЯ ФРОНТА ====================

def build_subscription_state(db, user_id: int) -> dict:
    """Статус подписки пользователя в виде JSON для Mini App."""
    keys = db.get_user_keys(user_id)
    sub = db.get_active_subscription(user_id)

    has_key = len(keys) > 0
    status = "none"
    expires_at = None
    created_at = None
    plan = None

    if has_key:
        # Берём ключ с самым поздним сроком окончания (None = бессрочно = «самый поздний»).
        # Так после продления оплатой показывается актуальный (продлённый) ключ,
        # а не первый по порядку (например, ещё активный пробный).
        def _key_expiry(k):
            dt = _parse_dt(k[7])
            return dt or datetime.max

        key = max(keys, key=_key_expiry)
        created_at = _parse_dt(key[6])
        expires_at = _parse_dt(key[7])
        if sub:
            plan = sub[4]  # duration_type
        status = "trial" if plan == "trial" else "active"

    now = datetime.now()
    days_left = None
    progress = 0
    expires_human = None
    forever = False

    if has_key:
        if expires_at is None:
            forever = True
            status = "active"
            days_left = None
            progress = 100
            expires_human = "Навсегда"
        elif expires_at <= now:
            status = "expired"
            days_left = 0
            progress = 0
            expires_human = expires_at.strftime("%d.%m.%Y")
        else:
            delta = expires_at - now
            days_left = delta.days
            expires_human = expires_at.strftime("%d.%m.%Y %H:%M")
            if created_at:
                total = (expires_at - created_at).total_seconds()
                elapsed = (now - created_at).total_seconds()
                progress = max(0, min(100, int((1 - elapsed / total) * 100))) if total > 0 else 100
            else:
                progress = 100

    return {
        "status": status,           # none | trial | active | expired
        "has_key": has_key,
        "forever": forever,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "expires_human": expires_human,
        "days_left": days_left,
        "progress": progress,
        "sub_url": get_subscription_url(user_id) if has_key else None,
        "plan": plan,
    }


def build_state(db, user: dict) -> dict:
    """Полное состояние для главного экрана Mini App."""
    user_id = int(user["id"])

    db.add_user(user_id, user.get("username"), user.get("first_name"))

    balance = db.get_user_balance(user_id)
    referral_count = db.get_referral_count(user_id)
    blocked = db.is_user_blocked(user_id)

    tariffs = [
        {
            "plan": key,
            "title": PLAN_TITLE[key],
            "price": PRICES[key],
            "days": PLAN_DAYS[key],
            "badge": PLAN_BADGE.get(key),
            "per_month": round(PRICES[key] / (PLAN_DAYS[key] / 30)),
        }
        for key in PLAN_ORDER
        if key in PRICES
    ]

    return {
        "ok": True,
        "user": {
            "id": user_id,
            "first_name": user.get("first_name", ""),
            "username": user.get("username"),
            "photo_url": user.get("photo_url"),
            "is_premium": bool(user.get("is_premium")),
        },
        "is_admin": is_admin(user_id),
        "blocked": blocked,
        "needs_channel": (not blocked) and (not check_channel_membership(user_id)),
        "channel": {"username": CHANNEL_USERNAME.lstrip("@"), "title": CHANNEL_USERNAME},
        "subscription": build_subscription_state(db, user_id),
        "wallet": {"balance": balance["balance"], "bonus_hours": balance["bonus_hours"]},
        "referral": {
            "count": referral_count,
            "link": get_referral_link(user_id),
            "bonus_hours": balance["bonus_hours"],
        },
        "tariffs": tariffs,
        # Лёгкая часть про устройства (без обращения к панели). Живой счётчик
        # подключённых устройств подгружается отдельно через /api/devices.
        "devices": {
            "limit": db.get_device_limit(user_id),
            "default": DEVICE_LIMIT_DEFAULT,
            "pack_size": DEVICE_PACK_SIZE,
            "pack_price": DEVICE_PACK_PRICE,
            "has_key": bool(db.get_active_key_email(user_id)),
        },
        "trial_available": (not db.has_used_trial(user_id)) and (db.get_active_subscription(user_id) is None),
        "trial_days": TRIAL_DAYS,
        "payment": {
            "crypto_enabled": True,
            "card_ru": CARD_RU,
            "card_ua": CARD_UA,
        },
        "brand": {"name": VPN_NAME, "server": "Эстония", "flag": "🇪🇪"},
    }
