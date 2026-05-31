"""
Токены для ссылок подписки (/sub/, /app/, /config/) и реферальных ссылок.

Безопасная схема v1:  "v1" + base64url(user_id) + base64url(HMAC-SHA256(secret, user_id)[:12])
  • подпись HMAC делает токен НЕПОДДЕЛЫВАЕМЫМ: без серверного секрета
    нельзя сгенерировать валидный токен под чужой user_id, перебор бесполезен;
  • используются только символы [A-Za-z0-9_-] + префикс "v1" — токен валиден
    и в URL, и в Telegram deep-link (?start=ref_...).

Старая XOR-схема (без подписи, ПОДДЕЛЫВАЕМАЯ) поддерживается только как
fallback для ссылок, выданных раньше, и только пока config.ALLOW_LEGACY_TOKENS
= True. Когда пользователи переоткроют приложение и заберут новую ссылку,
поставьте ALLOW_LEGACY_TOKENS = False — старые токены перестанут приниматься,
и дыру с перебором/подделкой ссылок закроет полностью.
"""

import base64
import hashlib
import hmac

from config import BOT_TOKEN

try:
    from config import ALLOW_LEGACY_TOKENS
except Exception:
    ALLOW_LEGACY_TOKENS = True

# Отдельные секреты: для подписи новых токенов и для расшифровки старых.
_SIGN_KEY = hashlib.sha256(b"aeroproject-subtoken-v1:" + BOT_TOKEN.encode()).digest()
_LEGACY_KEY = hashlib.sha256(BOT_TOKEN.encode()).digest()

_PREFIX = "v1"
_SIG_BYTES = 12          # 96-битная подпись
_SIG_CHARS = 16          # base64url(12 байт) = ровно 16 символов, без '='


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _sign(payload: bytes) -> bytes:
    return hmac.new(_SIGN_KEY, payload, hashlib.sha256).digest()[:_SIG_BYTES]


def encrypt_user_id(user_id: int) -> str:
    """Подписанный (неподделываемый) токен для user_id."""
    payload = str(int(user_id)).encode()
    return _PREFIX + _b64e(payload) + _b64e(_sign(payload))


def _decrypt_secure(token: str):
    if not token.startswith(_PREFIX):
        return None
    body = token[len(_PREFIX):]
    if len(body) <= _SIG_CHARS:
        return None
    payload_part, sig_part = body[:-_SIG_CHARS], body[-_SIG_CHARS:]
    try:
        payload = _b64d(payload_part)
        sig = _b64d(sig_part)
    except Exception:
        return None
    if not hmac.compare_digest(sig, _sign(payload)):
        return None
    try:
        return int(payload.decode())
    except Exception:
        return None


def _decrypt_legacy(token: str):
    """Старая XOR-схема (подделываемая) — только для совместимости."""
    try:
        padding = 4 - len(token) % 4
        if padding != 4:
            token += "=" * padding
        encrypted = base64.urlsafe_b64decode(token.encode())
        user_bytes = bytes(b ^ _LEGACY_KEY[i % len(_LEGACY_KEY)] for i, b in enumerate(encrypted))
        return int(user_bytes.decode())
    except Exception:
        return None


def decrypt_token(token: str):
    """Вернуть user_id из токена. Сначала безопасная схема, затем (если
    разрешено флагом) старая. None — если токен невалиден."""
    if not token:
        return None
    uid = _decrypt_secure(token)
    if uid is not None:
        return uid
    if ALLOW_LEGACY_TOKENS:
        return _decrypt_legacy(token)
    return None


def generate_referral_link(user_id: int, bot_username: str = "AeroProjectVPN_bot") -> str:
    """Generate referral link for user."""
    return f"https://t.me/{bot_username}?start=ref_{encrypt_user_id(user_id)}"
