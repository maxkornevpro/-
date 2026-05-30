"""
Inline-клавиатуры бота AeroProjectVPN.

Telegram не позволяет напрямую красить кнопки, поэтому "цвет" задаётся
через цветные эмодзи (🟢🔵🟣🟡🔴) и тематические иконки — это создаёт
премиальный, акцентный вид меню.
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

SUPPORT_URL = "https://t.me/PavelEndurov"


# ==================== ГЛАВНОЕ МЕНЮ ====================
def main_menu(has_active_key=False, is_admin=False):
    builder = InlineKeyboardBuilder()

    if not has_active_key:
        builder.button(text="🎁 Попробовать бесплатно · 1 день", callback_data="trial")
        builder.button(text="🟢 Купить VPN", callback_data="buy")
        builder.button(text="🔑 Мой ключ", callback_data="my_key")
    else:
        builder.button(text="🔑 Мой ключ", callback_data="my_key")
        builder.button(text="🟢 Продлить / купить", callback_data="buy")

    builder.button(text="📲 Как подключить", callback_data="help")
    builder.button(text="🎁 Пригласить друга", callback_data="referral")
    builder.button(text="💬 Поддержка 24/7", url=SUPPORT_URL)

    if is_admin:
        builder.button(text="🛠 Админ-панель", callback_data="admin_panel")

    # Раскладка: верхние акценты по одному, затем парами
    if not has_active_key:
        # trial | buy | my_key | help+referral | support | (admin)
        if is_admin:
            builder.adjust(1, 1, 1, 2, 1, 1)
        else:
            builder.adjust(1, 1, 1, 2, 1)
    else:
        if is_admin:
            builder.adjust(2, 2, 1, 1)
        else:
            builder.adjust(2, 2, 1)
    return builder.as_markup()


# ==================== ПРОВЕРКА ПОДПИСКИ НА КАНАЛ ====================
def check_subscription_keyboard(channel_username):
    builder = InlineKeyboardBuilder()
    builder.button(
        text="📢 Подписаться на канал",
        url=f"https://t.me/{channel_username.replace('@', '')}",
    )
    builder.button(text="✅ Я подписался", callback_data="check_sub")
    builder.adjust(1)
    return builder.as_markup()


# ==================== МЕНЮ ПОКУПКИ ====================
def purchase_menu():
    builder = InlineKeyboardBuilder()
    builder.button(text="🥉 1 месяц · 100₽", callback_data="buy_1_month")
    builder.button(text="🥈 6 месяцев · 225₽  🔥 выгодно", callback_data="buy_6_months")
    builder.button(text="🥇 1 год · 400₽  💎 хит", callback_data="buy_1_year")
    builder.button(text="◀️ Назад", callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()


# ==================== ВЫБОР СПОСОБА ОПЛАТЫ ====================
def payment_methods(plan, crypto_enabled=True):
    builder = InlineKeyboardBuilder()
    if crypto_enabled:
        builder.button(text="🟣 CryptoPay · крипта", callback_data=f"pay_crypto_{plan}")
    builder.button(text="🔵 Карта РФ", callback_data=f"pay_card_ru_{plan}")
    builder.button(text="🟡 Карта UA", callback_data=f"pay_card_ua_{plan}")
    builder.button(text="◀️ Назад", callback_data="buy")
    builder.adjust(1)
    return builder.as_markup()


# ==================== АДМИН-ПАНЕЛЬ ====================
def admin_menu():
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Статистика", callback_data="admin_stats")
    builder.button(text="👥 Пользователи", callback_data="admin_users")
    builder.button(text="🔑 Все ключи", callback_data="admin_keys")
    builder.button(text="📋 Заказы", callback_data="admin_orders")
    builder.button(text="📢 Рассылка /all", callback_data="admin_broadcast")
    builder.button(text="🔄 Рестарт сервера", callback_data="admin_restart")
    builder.button(text="◀️ В главное меню", callback_data="back_to_main")
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup()


# ==================== ПОДТВЕРЖДЕНИЕ ОПЛАТЫ (для админа) ====================
def confirm_payment_keyboard(order_id):
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить", callback_data=f"confirm_pay_{order_id}")
    builder.button(text="❌ Отклонить", callback_data=f"reject_pay_{order_id}")
    builder.adjust(2)
    return builder.as_markup()


# ==================== КНОПКА НАЗАД ====================
def back_button(callback_data="back_to_main"):
    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Назад", callback_data=callback_data)
    return builder.as_markup()


# ==================== ДЕЙСТВИЯ С КЛЮЧОМ ====================
def key_actions(connect_url=None):
    builder = InlineKeyboardBuilder()
    if connect_url:
        builder.button(text="⚡️ Быстрое подключение", url=connect_url)
    builder.button(text="📋 Скопировать ключ", callback_data="copy_key")
    builder.button(text="🔄 Обновить ключ", callback_data="renew_key")
    builder.button(text="📲 Инструкция", callback_data="help")
    builder.button(text="◀️ Назад", callback_data="back_to_main")
    if connect_url:
        builder.adjust(1, 2, 1, 1)
    else:
        builder.adjust(2, 1, 1)
    return builder.as_markup()


# ==================== РЕФЕРАЛЬНОЕ МЕНЮ ====================
def referral_menu(share_url):
    builder = InlineKeyboardBuilder()
    builder.button(text="📤 Поделиться ссылкой", url=share_url)
    builder.button(text="◀️ Назад", callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()
