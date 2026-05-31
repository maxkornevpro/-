# Bot configuration
import os

BOT_TOKEN = "8757331587:AAH0PUsD4xV1GIZFMdDg4OJo5aeWJGOEYVE"

# Channel settings
CHANNEL_USERNAME = "@AeroProjectVpn"
CHANNEL_ID = -1003773406536

# Admin settings
ADMIN_USERNAME = "@PavelEndurov"
ADMIN_IDS = [1246190987]

# Bot username (used for referral links)
BOT_USERNAME = "AeroProjectVPN_bot"

# ==================== VPN SERVER - ESTONIA (only server) ====================
VPS2_HOST = "95.85.249.79"
VPS2_DOMAIN = "ee.aeroproject.fun"
VPS2_USER = "root"
VPS2_PASSWORD = "FNvhSI1r4VVdbj7G"
VPS2_PORT = 8443
VPS2_PUBLIC_KEY = "t866kDCHHb2R3aGvwWpyQ1a8UpWXanzY3Pt6LX8Dzw8"
VPS2_SHORT_ID = "8f7c67"

# 3x-ui Panel Settings - Estonia
VPS2_3XUI_PORT = 2053
VPS2_3XUI_USERNAME = "admin"
VPS2_3XUI_PASSWORD = "AeroEE_3xUi!2026"

# Branding
VPN_NAME = "AeroProjectVPN"
VPN_WEB_URL = "https://ee.aeroproject.fun"
# Публичные URL отдаются через nginx на 443 (валидный SSL от certbot),
# а nginx проксирует пути на локальные HTTP-бэкенды:
#   /sub/, /api/sub/, /config/  ->  127.0.0.1:9091  (subscription_api)
#   /tgapp/                     ->  127.0.0.1:9090  (webapp_api, Mini App)
# Поэтому в публичных URL НЕ должно быть портов 9090/9091 — это локальные
# HTTP-порты без TLS, и Telegram Mini App по ним не откроется.
SUBSCRIPTION_BASE_URL = "https://ee.aeroproject.fun"

# ==================== TELEGRAM MINI APP ====================
# Публичный HTTPS-URL Mini App (отдаётся nginx'ом, проксируется на WEBAPP_PORT).
WEBAPP_URL = "https://ee.aeroproject.fun/tgapp/"
# Локальный порт, на котором слушает aiohttp-бэкенд Mini App.
# 9091 занят subscription_api, поэтому Mini App — на 9090.
WEBAPP_PORT = 9090
# Требовать подписку на канал перед доступом к приложению.
CHANNEL_REQUIRED = True
# Реквизиты для оплаты картой (показываются в Mini App).
CARD_RU = "2204120131636421"
CARD_UA = ""  # если пусто — кнопка «Карта UA» отправляет к админу за реквизитами

# Pricing (RUB). Сервер стоит ~180₽/мес — тарифы выстроены так, чтобы
# даже один платящий пользователь окупал содержание, а длинные планы
# давали скидку за мес. и стимулировали предоплату.
PRICES = {
    "1_month": 149,
    "3_months": 399,
    "6_months": 699,
    "1_year": 1190,
}

# Trial settings
TRIAL_DAYS = 1
# Лимит трафика на пробный период, ГБ (0 = безлимит). На платных тарифах — безлимит.
TRIAL_TRAFFIC_GB = 50

# ==================== УСТРОЙСТВА (одновременные подключения) ====================
# Сколько устройств доступно по умолчанию (без докупки).
DEVICE_LIMIT_DEFAULT = 2
# Всего максимум устройств на пользователя.
DEVICE_MAX = 12
# Максимум устройств, которые можно докупить за одну покупку.
DEVICE_MAX_BUY = 10
# Цена за ОДНО устройство, ₽ (итог = количество × цена).
DEVICE_PRICE = 49

# Совместимость со старым кодом (не используются в новой логике докупки).
DEVICE_PACK_SIZE = DEVICE_MAX_BUY
DEVICE_PACK_PRICE = DEVICE_PRICE * DEVICE_MAX_BUY

# Database
DB_FILE = os.path.join(os.path.dirname(__file__), "vpn_bot.db")

# ==================== БЕЗОПАСНОСТЬ ====================
# Принимать старые (XOR, подделываемые) токены ссылок подписки.
# Держите True, пока часть пользователей не переоткрыла приложение и не
# забрала новую безопасную ссылку. Поставьте False, чтобы полностью закрыть
# возможность подделки/перебора ссылок /sub/ /app/ /config/.
ALLOW_LEGACY_TOKENS = True

# CryptoBot
CRYPTO_BOT_TOKEN = "561879:AAGlQg1ZepeCv70Q9CSqr73tbK2Or0289Uv"

# ==================== PREMIUM STICKERS ====================
# Telegram sticker file_id'ы для красивого оформления.
# Бот отправляет их при разных событиях. Если file_id пустой или
# невалидный — отправка просто пропускается (бот не ломается).
#
# Как получить свои премиум/анимированные стикеры:
#   1. Отправь любой стикер боту в личку.
#   2. Бот ответит его file_id (см. обработчик в bot.py).
#   3. Вставь file_id в нужное поле ниже.
STICKERS = {
    "welcome": "",   # приветствие в /start
    "trial": "",     # выдача пробного доступа
    "success": "",   # успешная оплата / выдача ключа
    "key": "",       # показ ключа
    "error": "",     # ошибка
}
