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
SUBSCRIPTION_BASE_URL = "https://ee.aeroproject.fun"

# ==================== TELEGRAM MINI APP ====================
# Публичный HTTPS-URL Mini App (отдаётся nginx'ом, проксируется на WEBAPP_PORT).
WEBAPP_URL = "https://ee.aeroproject.fun/tgapp/"
# Локальный порт, на котором слушает aiohttp-бэкенд Mini App.
WEBAPP_PORT = 8090
# Требовать подписку на канал перед доступом к приложению.
CHANNEL_REQUIRED = True
# Реквизиты для оплаты картой (показываются в Mini App).
CARD_RU = "2204120131636421"
CARD_UA = ""  # если пусто — кнопка «Карта UA» отправляет к админу за реквизитами

# Pricing
PRICES = {
    "1_month": 100,
    "6_months": 225,
    "1_year": 400,
}

# Trial settings
TRIAL_DAYS = 1

# Database
DB_FILE = os.path.join(os.path.dirname(__file__), "vpn_bot.db")

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
