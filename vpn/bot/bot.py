#!/usr/bin/env python3
"""
AeroProjectVPN — Telegram bot
- Проверка подписки на канал
- Пробный доступ (1 день)
- Покупка подписки (1 мес — 100₽, 6 мес — 225₽, 1 год — 400₽)
- Генерация VLESS-ключей (сервер: Эстония)
- Реферальная программа
- Премиум-оформление: цветные кнопки + стикеры
- Админ-панель
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiocryptopay import AioCryptoPay, Networks

from config import (
    BOT_TOKEN, CHANNEL_USERNAME, CHANNEL_ID,
    ADMIN_IDS, ADMIN_USERNAME, PRICES, TRIAL_DAYS,
    VPS2_HOST, VPS2_USER, VPS2_PASSWORD, VPS2_PORT,
    VPN_NAME, VPN_WEB_URL, CRYPTO_BOT_TOKEN, SUBSCRIPTION_BASE_URL,
    BOT_USERNAME, STICKERS,
)
from database import Database
from vpn_manager import VPNManager
from keyboards import (
    main_menu, check_subscription_keyboard, purchase_menu, payment_methods,
    admin_menu, confirm_payment_keyboard, back_button, key_actions, referral_menu,
)
from token_crypto import encrypt_user_id, decrypt_token, generate_referral_link

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize bot and dispatcher
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Initialize CryptoPay
cryptopay = AioCryptoPay(token=CRYPTO_BOT_TOKEN, network=Networks.MAIN_NET) if CRYPTO_BOT_TOKEN else None

# Initialize database
db = Database()

# Визуальные разделители для премиум-оформления
DIV = "➖➖➖➖➖➖➖➖➖➖➖➖"
LINE = "━━━━━━━━━━━━━━"

# ==================== HELPER FUNCTIONS ====================

def is_admin(user_id: int) -> bool:
    """Check if user is admin."""
    return user_id in ADMIN_IDS


async def send_sticker_safe(chat_id: int, key: str):
    """Безопасно отправить стикер по ключу из config.STICKERS.

    Если file_id пустой или невалидный — просто пропускаем,
    чтобы бот никогда не падал из-за стикеров.
    """
    file_id = STICKERS.get(key)
    if not file_id:
        return
    try:
        await bot.send_sticker(chat_id, file_id)
    except Exception as exc:
        logger.warning(f"Не удалось отправить стикер '{key}': {exc}")


def get_subscription_url(user_id: int) -> str:
    """Return the standard subscription URL."""
    sub_token = encrypt_user_id(user_id)
    return f"{SUBSCRIPTION_BASE_URL}/sub/{sub_token}"


def get_connect_url(user_id: int) -> str:
    """Ссылка на красивую страницу подключения (с кнопками приложений)."""
    sub_token = encrypt_user_id(user_id)
    return f"{SUBSCRIPTION_BASE_URL}/app/{sub_token}"


def render_subscription_links(user_id: int, title: str = "Твоя защищённая ссылка подписки") -> str:
    """Render the standard subscription URL."""
    sub_url = get_subscription_url(user_id)
    return (
        f"🛡 <b>{title}:</b>\n"
        f"<code>{sub_url}</code>\n\n"
        f"📋 <i>Нажми на ссылку, чтобы скопировать</i>"
    )


async def check_user_subscription(user_id: int) -> bool:
    """Check if user is subscribed to channel."""
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except TelegramBadRequest:
        return False
    except Exception as e:
        logger.error(f"Error checking subscription: {e}")
        return False


def format_time_left(end_date_str):
    """Format time left until subscription ends."""
    if not end_date_str:
        return "♾️ Навсегда"
    try:
        end_date = datetime.fromisoformat(str(end_date_str).replace('Z', '+00:00').replace('+00:00', ''))
        now = datetime.now()
        diff = end_date - now

        if diff.days > 365:
            return "♾️ Навсегда"
        elif diff.days > 0:
            hours = diff.seconds // 3600
            return f"📅 {diff.days} дн. {hours} ч."
        elif diff.seconds > 3600:
            return f"⏰ {diff.seconds // 3600} часов"
        elif diff.seconds > 60:
            return f"⏰ {diff.seconds // 60} минут"
        else:
            return "⏰ Менее минуты"
    except Exception:
        return "Неизвестно"


def format_expiry_date(end_date_str):
    """Format expiry date for display."""
    if not end_date_str:
        return "01.01.2099"
    try:
        end_date = datetime.fromisoformat(str(end_date_str).replace('Z', '+00:00').replace('+00:00', ''))
        return end_date.strftime('%d.%m.%Y')
    except Exception:
        return "Неизвестно"


def get_subscription_progress(start_date, end_date):
    """Calculate subscription progress bar."""
    if not start_date or not end_date:
        return "🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩"
    try:
        start = datetime.fromisoformat(str(start_date).replace('Z', '+00:00').replace('+00:00', ''))
        end = datetime.fromisoformat(str(end_date).replace('Z', '+00:00').replace('+00:00', ''))
        now = datetime.now()

        if now >= end:
            return "⬛️⬛️⬛️⬛️⬛️⬛️⬛️⬛️⬛️⬛️ Истекла"

        total = (end - start).total_seconds()
        elapsed = (now - start).total_seconds()
        filled = min(int((elapsed / total) * 10), 10)
        left = 10 - filled

        bar = "🟩" * left + "⬛️" * filled
        return bar
    except Exception:
        return "🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩"


def welcome_text(first_name: str | None = None) -> str:
    """Главный приветственный текст (премиум-оформление)."""
    greeting = f"👋 Привет, <b>{first_name}</b>!\n\n" if first_name else ""
    return (
        f"{greeting}"
        f"🛡 <b>{VPN_NAME}</b> — твой ключ к свободному интернету\n"
        f"{DIV}\n"
        f"🇪🇪 <b>Сервер:</b> Эстония · супербыстрый\n"
        f"🔒 <b>Протокол:</b> VLESS-Reality (без логов)\n"
        f"👻 <b>Анонимность:</b> провайдер не видит VPN\n"
        f"♾️ <b>Трафик:</b> безлимит и без ограничений\n"
        f"{DIV}\n"
        f"💎 <b>Тарифы:</b>\n"
        f"🥉 1 месяц — <b>{PRICES['1_month']}₽</b>\n"
        f"🥈 6 месяцев — <b>{PRICES['6_months']}₽</b>  🔥\n"
        f"🥇 1 год — <b>{PRICES['1_year']}₽</b>  💎\n"
        f"{DIV}\n"
        f"💬 По вопросам: {ADMIN_USERNAME}\n"
        f"👇 Выбери действие:"
    )


# ==================== HANDLERS ====================

@dp.message(CommandStart())
async def cmd_start(message: Message):
    """Start command handler with referral support."""
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name

    # Check if user is blocked
    if db.is_user_blocked(user_id):
        await message.answer(
            "🚫 <b>Твой аккаунт заблокирован</b>\n\n"
            "Обратись к администратору:",
            reply_markup=InlineKeyboardBuilder().button(
                text="💬 Поддержка", url=f"https://t.me/{ADMIN_USERNAME.replace('@', '')}"
            ).as_markup(),
            parse_mode=ParseMode.HTML
        )
        return

    # Check for referral in start command
    referrer_id = None
    if message.text and len(message.text.split()) > 1:
        param = message.text.split()[1]
        if param.startswith('ref_'):
            try:
                encrypted_ref = param.replace('ref_', '')
                referrer_id = decrypt_token(encrypted_ref)
            except Exception:
                pass

    # Add user to database (with referrer if exists)
    db.add_user(user_id, username, first_name, referrer_id)

    # Check subscription
    is_subscribed = await check_user_subscription(user_id)

    if not is_subscribed:
        await message.answer(
            f"👋 Привет, <b>{first_name}</b>!\n\n"
            f"🛡 Добро пожаловать в <b>{VPN_NAME}</b>!\n"
            f"{DIV}\n"
            f"📢 Чтобы пользоваться ботом, подпишись на наш канал.\n"
            f"Это займёт пару секунд 👇",
            reply_markup=check_subscription_keyboard(CHANNEL_USERNAME),
            parse_mode=ParseMode.HTML
        )
        return

    # Check if user has active key
    keys = db.get_user_keys(user_id)
    has_active_key = len(keys) > 0

    user_is_admin = is_admin(user_id)
    await send_sticker_safe(message.chat.id, "welcome")
    await message.answer(
        welcome_text(first_name),
        reply_markup=main_menu(has_active_key=has_active_key, is_admin=user_is_admin),
        parse_mode=ParseMode.HTML
    )


@dp.callback_query(F.data == "check_sub")
async def check_subscription(callback: CallbackQuery):
    """Check subscription callback."""
    user_id = callback.from_user.id
    is_subscribed = await check_user_subscription(user_id)

    if is_subscribed:
        keys = db.get_user_keys(user_id)
        has_active_key = len(keys) > 0
        user_is_admin = is_admin(user_id)

        await callback.message.edit_text(
            f"✅ <b>Подписка подтверждена!</b>\n\n"
            + welcome_text(callback.from_user.first_name),
            reply_markup=main_menu(has_active_key=has_active_key, is_admin=user_is_admin),
            parse_mode=ParseMode.HTML
        )
    else:
        await callback.answer("❌ Ты ещё не подписался на канал!", show_alert=True)


@dp.callback_query(F.data == "trial")
async def get_trial(callback: CallbackQuery):
    """Get trial access."""
    user_id = callback.from_user.id

    # Check if already used trial
    if db.has_used_trial(user_id):
        await callback.answer("❌ Пробный доступ уже использован!", show_alert=True)
        return

    # Check if user has active subscription
    sub = db.get_active_subscription(user_id)
    if sub:
        await callback.answer("❌ У тебя уже есть активная подписка!", show_alert=True)
        return

    # Show loading message
    loading_msg = await callback.message.edit_text(
        "⚡️ <b>Создаю твой VPN-ключ...</b>\n"
        f"{DIV}\n"
        "🔧 Готовлю конфигурацию\n"
        "🇪🇪 Подключаю сервер Эстония\n"
        "🔐 Генерирую защищённый UUID\n\n"
        "<i>Секундочку...</i>",
        parse_mode=ParseMode.HTML
    )

    await asyncio.sleep(2)

    # Mark trial as used
    db.set_trial_used(user_id)

    # Generate trial key (1 day) - potentially slow (network/SSH/3x-ui)
    try:
        vpn = VPNManager()
        key_data = await asyncio.wait_for(
            asyncio.to_thread(vpn.generate_vpn_key, user_id, TRIAL_DAYS),
            timeout=90,
        )
    except Exception as exc:
        logger.error(f"Trial key generation failed for user {user_id}: {exc}")
        await send_sticker_safe(callback.message.chat.id, "error")
        await loading_msg.edit_text(
            "❌ <b>Не удалось выдать ключ</b>\n\n"
            "Сервер сейчас недоступен или перегружен. Попробуй ещё раз через 1-2 минуты.",
            reply_markup=back_button(),
            parse_mode=ParseMode.HTML,
        )
        return

    # Save to database
    db.add_vpn_key(
        user_id=user_id,
        uuid=key_data['uuid'],
        public_key=key_data['public_key'],
        private_key=key_data['private_key'],
        short_id=key_data['short_id'],
        expires_at=key_data['expires_at'],
        vless_link=key_data['vless_link'],
        server='estonia',
    )

    # Add trial subscription record
    db.add_subscription(user_id, "trial", 0, TRIAL_DAYS)

    expiry_date = (datetime.now() + timedelta(days=1)).strftime('%d.%m.%Y %H:%M')

    await send_sticker_safe(callback.message.chat.id, "trial")
    await loading_msg.edit_text(
        f"🎁 <b>Пробный доступ активирован!</b>\n"
        f"{DIV}\n"
        f"⏰ Срок: <b>1 день</b>\n"
        f"📅 Истекает: {expiry_date}\n"
        f"🇪🇪 Сервер: <b>Эстония (Fast)</b>\n"
        f"🔒 Шифрование: VLESS-Reality (без логов)\n"
        f"📱 Устройств: 1/1\n"
        f"{DIV}\n"
        f"{render_subscription_links(user_id)}\n\n"
        f"📲 <b>Как подключить (Happ):</b>\n"
        f"1️⃣ Скопируй ссылку подписки выше\n"
        f"2️⃣ Открой Happ → «Подписки»\n"
        f"3️⃣ Нажми ➕ → вставь ссылку\n"
        f"4️⃣ Сервер добавится автоматически\n\n"
        f"⚠️ <b>Важно:</b> ссылка работает на 1 устройстве!\n"
        f"💰 Для продления: {ADMIN_USERNAME}",
        reply_markup=key_actions(connect_url=get_connect_url(user_id)),
        parse_mode=ParseMode.HTML
    )


@dp.callback_query(F.data == "buy")
async def buy_menu(callback: CallbackQuery):
    """Show purchase menu with balance info."""
    user_id = callback.from_user.id
    balance_info = db.get_user_balance(user_id)
    referral_count = db.get_referral_count(user_id)

    balance_text = ""
    if balance_info['balance'] > 0:
        balance_text = f"💰 Твой баланс: <b>{balance_info['balance']}₽</b>\n"
    if referral_count > 0:
        balance_text += f"👥 Рефералов: {referral_count} (+{referral_count * 6}ч)\n"
    if balance_text:
        balance_text += f"{DIV}\n"

    await callback.message.edit_text(
        f"💎 <b>Покупка подписки</b>\n"
        f"{DIV}\n"
        f"{balance_text}"
        f"🛡 <b>Что внутри:</b>\n"
        f"• 🚫 Полное отсутствие логов (No Logs)\n"
        f"• 🔒 Шифрование VLESS-Reality\n"
        f"• 👻 Обход DPI: трафик как обычный сайт\n"
        f"• 🇪🇪 Сервер Эстония · супербыстрый\n"
        f"• ♾️ Безлимитный трафик\n"
        f"• 🛟 Поддержка 24/7\n"
        f"{DIV}\n"
        f"🥉 <b>1 месяц</b> — {PRICES['1_month']}₽\n"
        f"🥈 <b>6 месяцев</b> — {PRICES['6_months']}₽  🔥 выгода 60%\n"
        f"🥇 <b>1 год</b> — {PRICES['1_year']}₽  💎 максимум выгоды\n"
        f"{DIV}\n"
        f"👇 Выбери тариф:",
        reply_markup=purchase_menu(),
        parse_mode=ParseMode.HTML
    )


@dp.callback_query(F.data.startswith("buy_"))
async def process_purchase(callback: CallbackQuery):
    """Handle purchase selection - show payment method choice."""
    plan = callback.data.replace("buy_", "")
    user_id = callback.from_user.id

    price = PRICES.get(plan, 0)
    duration_text = {
        "1_month": "1 месяц",
        "6_months": "6 месяцев",
        "1_year": "1 год"
    }.get(plan, plan)

    await callback.message.edit_text(
        f"💳 <b>Способ оплаты</b>\n"
        f"{DIV}\n"
        f"📦 Тариф: <b>{duration_text}</b>\n"
        f"💰 К оплате: <b>{price}₽</b>\n"
        f"{DIV}\n"
        f"👇 Выбери удобный способ:",
        reply_markup=payment_methods(plan, crypto_enabled=bool(cryptopay)),
        parse_mode=ParseMode.HTML
    )


@dp.callback_query(F.data.startswith("pay_crypto_"))
async def pay_with_crypto(callback: CallbackQuery):
    """Process payment via CryptoBot."""
    plan = callback.data.replace("pay_crypto_", "")
    user_id = callback.from_user.id
    username = callback.from_user.username

    price = PRICES.get(plan, 0)
    duration_text = {
        "1_month": "1 месяц",
        "6_months": "6 месяцев",
        "1_year": "1 год"
    }.get(plan, plan)

    if not cryptopay:
        await callback.answer("CryptoBot не настроен.", show_alert=True)
        return

    try:
        invoice = await cryptopay.create_invoice(
            amount=price,
            fiat='RUB',
            currency_type='fiat',
            description=f"Оплата VPN ({duration_text})"
        )

        order_id = db.create_order(user_id, username, plan, price, invoice.invoice_id)

        kb = InlineKeyboardBuilder()
        kb.button(text="💳 Оплатить", url=invoice.bot_invoice_url)
        kb.button(text="🔄 Проверить оплату", callback_data=f"check_pay_{order_id}")
        kb.button(text="◀️ Назад", callback_data="buy")
        kb.adjust(1)

        await callback.message.edit_text(
            f"🟣 <b>Оплата через CryptoBot</b>\n"
            f"{DIV}\n"
            f"📦 Тариф: <b>{duration_text}</b>\n"
            f"💰 К оплате: <b>{price}₽</b>\n"
            f"{DIV}\n"
            f"1️⃣ Нажми «💳 Оплатить»\n"
            f"2️⃣ Оплати счёт в CryptoBot\n"
            f"3️⃣ Вернись и нажми «🔄 Проверить оплату»",
            reply_markup=kb.as_markup(),
            parse_mode=ParseMode.HTML
        )

        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(
                    admin_id,
                    f"⏳ Пользователь @{username or user_id} создал счёт на {duration_text} через CryptoBot.",
                    parse_mode=ParseMode.HTML
                )
            except Exception:
                pass
    except Exception as e:
        logger.error(f"CryptoPay error: {e}")
        await callback.answer("Ошибка создания платежа.", show_alert=True)


@dp.callback_query(F.data.startswith("pay_card_ru_"))
async def pay_with_card_ru(callback: CallbackQuery):
    """Process payment via Russian card."""
    plan = callback.data.replace("pay_card_ru_", "")
    user_id = callback.from_user.id
    username = callback.from_user.username

    price = PRICES.get(plan, 0)
    duration_text = {
        "1_month": "1 месяц",
        "6_months": "6 месяцев",
        "1_year": "1 год"
    }.get(plan, plan)

    order_id = db.create_order(user_id, username, plan, price)

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"🛒 <b>Новый заказ (Карта РФ)!</b>\n\n"
                f"👤 Пользователь: @{username or user_id}\n"
                f"🆔 ID: <code>{user_id}</code>\n"
                f"📦 Тариф: {duration_text}\n"
                f"💰 Сумма: {price}₽\n"
                f"📋 Order ID: {order_id}\n\n"
                f"❗️ Ожидает подтверждения оплаты",
                reply_markup=confirm_payment_keyboard(order_id),
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Failed to notify admin {admin_id}: {e}")

    await callback.message.edit_text(
        f"🔵 <b>Заказ #{order_id} создан!</b>\n"
        f"{DIV}\n"
        f"📦 Тариф: <b>{duration_text}</b>\n"
        f"💰 Сумма: <b>{price}₽</b>\n"
        f"{DIV}\n"
        f"💳 <b>Реквизиты (Карта РФ):</b>\n"
        f"<code>2204120131636421</code>\n\n"
        f"✅ После оплаты напиши администратору:\n"
        f"{ADMIN_USERNAME}\n"
        f"📋 Укажи Order ID: <code>{order_id}</code>",
        reply_markup=back_button(),
        parse_mode=ParseMode.HTML
    )


@dp.callback_query(F.data.startswith("pay_card_ua_"))
async def pay_with_card_ua(callback: CallbackQuery):
    """Process payment via Ukrainian card."""
    plan = callback.data.replace("pay_card_ua_", "")
    user_id = callback.from_user.id
    username = callback.from_user.username

    price = PRICES.get(plan, 0)
    duration_text = {
        "1_month": "1 месяц",
        "6_months": "6 месяцев",
        "1_year": "1 год"
    }.get(plan, plan)

    order_id = db.create_order(user_id, username, plan, price)

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"🛒 <b>Новый заказ (Карта UA)!</b>\n\n"
                f"👤 Пользователь: @{username or user_id}\n"
                f"🆔 ID: <code>{user_id}</code>\n"
                f"📦 Тариф: {duration_text}\n"
                f"💰 Сумма: {price}₽\n"
                f"📋 Order ID: {order_id}\n\n"
                f"❗️ Ожидает подтверждения оплаты",
                reply_markup=confirm_payment_keyboard(order_id),
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Failed to notify admin {admin_id}: {e}")

    await callback.message.edit_text(
        f"🟡 <b>Заказ #{order_id} создан!</b>\n"
        f"{DIV}\n"
        f"📦 Тариф: <b>{duration_text}</b>\n"
        f"💰 Сумма: <b>{price}₽</b>\n"
        f"{DIV}\n"
        f"🇺🇦 <b>Реквизиты (Карта UA):</b>\n"
        f"Напиши администратору для получения реквизитов:\n"
        f"{ADMIN_USERNAME}\n"
        f"📋 Order ID: <code>{order_id}</code>",
        reply_markup=back_button(),
        parse_mode=ParseMode.HTML
    )


@dp.callback_query(F.data.startswith("check_pay_"))
async def check_crypto_payment(callback: CallbackQuery):
    if not cryptopay:
        await callback.answer("CryptoBot не настроен.", show_alert=True)
        return

    order_id = int(callback.data.replace("check_pay_", ""))
    db.cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
    order = db.cursor.fetchone()

    if not order or order[5] != 'pending':
        await callback.answer("❌ Заказ не найден или уже оплачен!", show_alert=True)
        return

    invoice_id = order[8]  # index 8 is invoice_id
    if not invoice_id:
        await callback.answer("❌ Ошибка платежа.", show_alert=True)
        return

    try:
        invoices = await cryptopay.get_invoices(invoice_ids=invoice_id)
        if not invoices:
            await callback.answer("Счёт не найден.", show_alert=True)
            return

        invoice = invoices[0]
        if invoice.status == 'paid':
            await callback.message.edit_text("⚡️ Обработка платежа и выдача ключа...")

            user_id = order[1]
            duration_type = order[3]

            db.mark_order_paid(order_id)

            days = None
            if duration_type == "1_month":
                days = 30
            elif duration_type == "6_months":
                days = 180
            elif duration_type == "1_year":
                days = 365

            db.add_subscription(user_id, duration_type, order[4], days)

            # Cashback
            user_data = db.get_user(user_id)
            if user_data and user_data[6]:
                cashback = db.add_purchase_cashback(user_data[6], order[4])
                try:
                    await bot.send_message(
                        user_data[6],
                        f"🎉 <b>Кэшбэк получен!</b>\nТвой реферал совершил покупку!\n💰 +{cashback}₽ на баланс",
                        parse_mode=ParseMode.HTML
                    )
                except Exception:
                    pass

            vpn = VPNManager()
            key_data = vpn.generate_vpn_key(user_id, days=days)

            db.add_vpn_key(
                user_id=user_id,
                uuid=key_data['uuid'],
                public_key=key_data['public_key'],
                private_key=key_data['private_key'],
                short_id=key_data['short_id'],
                expires_at=key_data['expires_at'],
                vless_link=key_data['vless_link'],
                server='estonia',
            )

            expiry_text = "♾️ Навсегда" if days is None else f"📅 {days} дней"
            await send_sticker_safe(callback.message.chat.id, "success")
            await callback.message.edit_text(
                f"✅ <b>Оплата получена!</b>\n"
                f"{DIV}\n"
                f"🎉 Тариф: <b>{duration_type}</b>\n"
                f"⏰ Срок: {expiry_text}\n"
                f"🇪🇪 Сервер: <b>Эстония (Fast)</b>\n"
                f"{DIV}\n"
                f"{render_subscription_links(user_id)}\n\n"
                f"📲 Вставь ссылку в Happ или v2rayNG",
                reply_markup=key_actions(connect_url=get_connect_url(user_id)),
                parse_mode=ParseMode.HTML
            )

            for admin_id in ADMIN_IDS:
                try:
                    await bot.send_message(
                        admin_id,
                        f"💰 <b>Новая оплата (CryptoBot)!</b>\nПользователь: @{order[2]}\nСумма: {order[4]}₽",
                        parse_mode=ParseMode.HTML
                    )
                except Exception:
                    pass
        else:
            await callback.answer("⏳ Оплата ещё не поступила. Попробуй через минуту.", show_alert=True)
    except Exception as e:
        logger.error(f"Check payment error: {e}")
        await callback.answer("Ошибка при проверке платежа.", show_alert=True)


@dp.callback_query(F.data == "my_key")
async def show_my_key(callback: CallbackQuery):
    """Show user's active key."""
    user_id = callback.from_user.id
    keys = db.get_user_keys(user_id)

    if not keys:
        await callback.message.edit_text(
            f"🚨 <b>{VPN_NAME}</b>\n"
            f"{DIV}\n"
            f"⏳ <b>У тебя нет активной подписки</b>\n\n"
            f"🎁 Получи пробный доступ\n"
            f"💎 Или купи подписку — всего от {PRICES['1_month']}₽",
            reply_markup=main_menu(has_active_key=False, is_admin=is_admin(user_id)),
            parse_mode=ParseMode.HTML
        )
        return

    key = keys[0]
    expires_at = key[7]
    created_at = key[6] if len(key) > 6 else None

    time_left = format_time_left(expires_at)
    expiry_date = format_expiry_date(expires_at)
    progress_bar = get_subscription_progress(created_at, expires_at)

    if "Истекла" in progress_bar:
        await callback.message.edit_text(
            f"🚨 <b>{VPN_NAME}</b>\n"
            f"{DIV}\n"
            f"⏳ <b>Подписка истекла</b>\n"
            f"📅 {expiry_date}\n\n"
            f"💎 Продлить подписку?",
            reply_markup=main_menu(has_active_key=False, is_admin=is_admin(user_id)),
            parse_mode=ParseMode.HTML
        )
        return

    await send_sticker_safe(callback.message.chat.id, "key")
    await callback.message.edit_text(
        f"🔑 <b>Твоя подписка {VPN_NAME}</b>\n"
        f"{DIV}\n"
        f"{progress_bar}\n"
        f"⏰ Осталось: {time_left}\n"
        f"📅 Истекает: {expiry_date}\n"
        f"🇪🇪 Сервер: <b>Эстония (Fast)</b>\n"
        f"🔒 Шифрование: VLESS-Reality (без логов)\n"
        f"📱 Устройств: 1/1\n"
        f"{DIV}\n"
        f"{render_subscription_links(user_id)}\n\n"
        f"📲 <b>Как подключить (Happ):</b>\n"
        f"1️⃣ Скопируй ссылку подписки\n"
        f"2️⃣ Открой Happ → «Подписки»\n"
        f"3️⃣ Вставь ссылку → сервер добавится",
        reply_markup=key_actions(connect_url=get_connect_url(user_id)),
        parse_mode=ParseMode.HTML
    )


@dp.callback_query(F.data == "copy_key")
async def copy_key(callback: CallbackQuery):
    """Just acknowledge the copy action."""
    await callback.answer("✅ Ключ скопирован! Вставь в приложение.", show_alert=True)


@dp.callback_query(F.data == "renew_key")
async def renew_key(callback: CallbackQuery):
    """Generate new key (for paid users)."""
    user_id = callback.from_user.id
    sub = db.get_active_subscription(user_id)

    if not sub:
        await callback.answer("❌ У тебя нет активной подписки!", show_alert=True)
        return

    # Get subscription duration
    duration_type = sub[4]
    days = 30
    if duration_type == "1_year":
        days = 365
    elif duration_type == "6_months":
        days = 180
    elif duration_type == "1_month":
        days = 30

    loading_msg = await callback.message.edit_text(
        "🔄 <b>Обновляю ключ...</b>\n"
        f"{DIV}\n"
        "⚡️ Генерирую новую конфигурацию\n\n"
        "<i>Секундочку...</i>",
        parse_mode=ParseMode.HTML
    )

    await asyncio.sleep(1.5)

    vpn = VPNManager()
    key_data = vpn.generate_vpn_key(user_id, days=days)

    db.add_vpn_key(
        user_id=user_id,
        uuid=key_data['uuid'],
        public_key=key_data['public_key'],
        private_key=key_data['private_key'],
        short_id=key_data['short_id'],
        expires_at=key_data['expires_at'],
        vless_link=key_data['vless_link'],
        server='estonia',
    )

    await loading_msg.edit_text(
        f"🔄 <b>Ссылка обновлена!</b>\n"
        f"{DIV}\n"
        f"{render_subscription_links(user_id, 'Новая ссылка подписки')}\n\n"
        f"⚠️ <b>Важно:</b> обнови ссылку в приложении!\n"
        f"📲 Старая ссылка больше не действительна",
        reply_markup=key_actions(connect_url=get_connect_url(user_id)),
        parse_mode=ParseMode.HTML
    )


@dp.callback_query(F.data == "help")
async def show_help(callback: CallbackQuery):
    """Show help/instructions."""
    connect_url = get_connect_url(callback.from_user.id)
    kb = InlineKeyboardBuilder()
    kb.button(text="⚡️ Открыть страницу подключения", url=connect_url)
    kb.button(text="◀️ Назад", callback_data="back_to_main")
    kb.adjust(1)

    await callback.message.edit_text(
        f"📲 <b>Инструкция по подключению</b>\n"
        f"{DIV}\n"
        f"🟢 <b>Самый простой способ:</b>\n"
        f"Нажми «⚡️ Открыть страницу подключения» — там кнопки для всех приложений.\n"
        f"{DIV}\n"
        f"🤖 <b>Android (v2rayNG / Happ):</b>\n"
        f"1️⃣ Установи приложение\n"
        f"2️⃣ ➕ → Импорт подписки из URL\n"
        f"3️⃣ Вставь ссылку → Подключить\n\n"
        f"🍏 <b>iOS (Happ / Streisand):</b>\n"
        f"1️⃣ Установи из App Store\n"
        f"2️⃣ ➕ → Импорт подписки\n"
        f"3️⃣ Подключить\n\n"
        f"🖥 <b>Windows (Nekoray / Hiddify):</b>\n"
        f"1️⃣ Скачай приложение\n"
        f"2️⃣ Добавь подписку из ссылки\n"
        f"3️⃣ Выбери сервер → Подключить\n"
        f"{DIV}\n"
        f"⚠️ 1 ключ = 1 устройство\n"
        f"💬 Проблемы? Пиши: {ADMIN_USERNAME}",
        reply_markup=kb.as_markup(),
        parse_mode=ParseMode.HTML
    )


@dp.callback_query(F.data == "referral")
async def referral_callback(callback: CallbackQuery):
    """Show referral program from main menu."""
    user_id = callback.from_user.id
    ref_link = generate_referral_link(user_id, BOT_USERNAME)
    balance_info = db.get_user_balance(user_id)
    referral_count = db.get_referral_count(user_id)

    share_url = (
        f"https://t.me/share/url?url={ref_link}"
        f"&text=" + "🛡 Подключайся к быстрому и анонимному VPN — первый день бесплатно!"
    )

    await callback.message.edit_text(
        f"🎁 <b>Реферальная программа</b>\n"
        f"{DIV}\n"
        f"🔗 <b>Твоя ссылка:</b>\n"
        f"<code>{ref_link}</code>\n"
        f"{DIV}\n"
        f"📊 <b>Статистика:</b>\n"
        f"👥 Приглашено: <b>{referral_count}</b>\n"
        f"⏰ Бонусные часы: <b>+{balance_info['bonus_hours']}ч</b>\n"
        f"💰 Баланс: <b>{balance_info['balance']}₽</b>\n"
        f"{DIV}\n"
        f"🎁 <b>Награды:</b>\n"
        f"• +6 часов VPN за каждого друга\n"
        f"• +2% с каждой покупки реферала\n\n"
        f"📤 Делись ссылкой и зарабатывай!",
        reply_markup=referral_menu(share_url),
        parse_mode=ParseMode.HTML
    )


@dp.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery):
    """Return to main menu."""
    user_id = callback.from_user.id
    keys = db.get_user_keys(user_id)
    has_active_key = len(keys) > 0

    user_is_admin = is_admin(user_id)
    await callback.message.edit_text(
        welcome_text(callback.from_user.first_name),
        reply_markup=main_menu(has_active_key=has_active_key, is_admin=user_is_admin),
        parse_mode=ParseMode.HTML
    )


@dp.callback_query(F.data == "admin_panel")
async def admin_panel_callback(callback: CallbackQuery):
    """Admin panel from callback."""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ У тебя нет доступа!", show_alert=True)
        return

    await callback.message.edit_text(
        f"🛠 <b>Админ-панель</b>\n"
        f"{DIV}\n"
        f"🤖 Бот: @{BOT_USERNAME}\n"
        f"🇪🇪 Сервер: Эстония\n\n"
        f"👇 Выбери действие:",
        reply_markup=admin_menu(),
        parse_mode=ParseMode.HTML
    )


@dp.message(Command("admin"))
async def admin_panel_command(message: Message):
    """Admin panel access via command."""
    if not is_admin(message.from_user.id):
        await message.answer("❌ У тебя нет доступа!")
        return

    await message.answer(
        f"🛠 <b>Админ-панель</b>\n"
        f"{DIV}\n"
        f"🤖 Бот: @{BOT_USERNAME}\n"
        f"🇪🇪 Сервер: Эстония\n\n"
        f"👇 Выбери действие:",
        reply_markup=admin_menu(),
        parse_mode=ParseMode.HTML
    )


@dp.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    """Show bot statistics."""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа!", show_alert=True)
        return

    stats = db.get_stats()
    vpn = VPNManager()
    try:
        server_status = vpn.get_server_status()
    except Exception:
        server_status = False

    await callback.message.edit_text(
        f"📊 <b>Статистика {VPN_NAME}</b>\n"
        f"{DIV}\n"
        f"👥 Всего пользователей: <b>{stats['total_users']}</b>\n"
        f"💎 Активных подписок: <b>{stats['active_subs']}</b>\n"
        f"🔑 Активных ключей: <b>{stats['active_keys']}</b>\n"
        f"{DIV}\n"
        f"🖥 <b>Сервер:</b>\n"
        f"🇪🇪 Эстония: {'🟢 online' if server_status else '🔴 offline'}\n"
        f"{DIV}\n"
        f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}",
        reply_markup=admin_menu(),
        parse_mode=ParseMode.HTML
    )


@dp.callback_query(F.data.startswith("confirm_pay_"))
async def confirm_payment(callback: CallbackQuery):
    """Confirm payment and generate key."""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа!", show_alert=True)
        return

    order_id = int(callback.data.replace("confirm_pay_", ""))

    db.cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
    order = db.cursor.fetchone()

    if not order or order[5] != 'pending':
        await callback.answer("❌ Заказ не найден или уже обработан!", show_alert=True)
        return

    user_id = order[1]
    duration_type = order[3]

    days = 365  # 1 year
    if duration_type == "1_month":
        days = 30
    elif duration_type == "6_months":
        days = 180

    db.mark_order_paid(order_id)
    db.add_subscription(user_id, duration_type, order[4], days)

    # Cashback to referrer (2% of purchase)
    user_data = db.get_user(user_id)
    if user_data and user_data[6]:  # referrer_id
        cashback = db.add_purchase_cashback(user_data[6], order[4])
        try:
            await bot.send_message(
                user_data[6],
                f"🎉 <b>Кэшбэк получен!</b>\n\n"
                f"Твой реферал совершил покупку!\n"
                f"💰 +{cashback}₽ на твой баланс\n"
                f"👥 Приглашай ещё друзей!",
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass

    vpn = VPNManager()
    key_data = vpn.generate_vpn_key(user_id, days=days)

    db.add_vpn_key(
        user_id=user_id,
        uuid=key_data['uuid'],
        public_key=key_data['public_key'],
        private_key=key_data['private_key'],
        short_id=key_data['short_id'],
        expires_at=key_data['expires_at'],
        vless_link=key_data['vless_link'],
        server='estonia',
    )

    expiry_text = "♾️ Навсегда" if days is None else f"📅 {days} дней"

    try:
        await send_sticker_safe(user_id, "success")
        await bot.send_message(
            user_id,
            f"✅ <b>Оплата подтверждена!</b>\n"
            f"{DIV}\n"
            f"🎉 Заказ #{order_id} оплачен\n"
            f"⏰ Срок: {expiry_text}\n"
            f"🇪🇪 Сервер: <b>Эстония (Fast)</b>\n"
            f"{DIV}\n"
            f"{render_subscription_links(user_id, 'Твоя ссылка подписки')}\n\n"
            f"📲 Добавь в Happ для автообновления\n"
            f"💎 Спасибо за покупку!",
            reply_markup=key_actions(connect_url=get_connect_url(user_id)),
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Failed to notify user {user_id}: {e}")

    await callback.message.edit_text(
        f"✅ Оплата подтверждена!\n"
        f"🔑 Ключ отправлен пользователю <code>{user_id}</code>",
        parse_mode=ParseMode.HTML
    )


@dp.callback_query(F.data.startswith("reject_pay_"))
async def reject_payment(callback: CallbackQuery):
    """Reject payment."""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа!", show_alert=True)
        return

    order_id = int(callback.data.replace("reject_pay_", ""))

    db.cursor.execute("SELECT user_id FROM orders WHERE id = ?", (order_id,))
    result = db.cursor.fetchone()

    db.cursor.execute("UPDATE orders SET status = 'rejected' WHERE id = ?", (order_id,))
    db.conn.commit()

    if result:
        try:
            await bot.send_message(
                result[0],
                f"❌ <b>Заказ #{order_id} отклонён</b>\n\n"
                f"Пожалуйста, свяжись с {ADMIN_USERNAME}",
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass

    await callback.message.edit_text("❌ Заказ отклонён")


@dp.callback_query(F.data == "admin_orders")
async def admin_orders(callback: CallbackQuery):
    """Show pending orders."""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа!", show_alert=True)
        return

    orders = db.get_pending_orders()

    if not orders:
        await callback.message.edit_text(
            "📋 Нет ожидающих заказов",
            reply_markup=admin_menu()
        )
        return

    text = "📋 <b>Ожидающие заказы:</b>\n\n"
    for order in orders:
        username = order[2] if order[2] else "Нет username"
        text += f"🆔 #{order[0]} | @{username} | {order[3]} | {order[4]}₽\n"

    await callback.message.edit_text(text, reply_markup=admin_menu(), parse_mode=ParseMode.HTML)


@dp.callback_query(F.data == "admin_restart")
async def admin_restart(callback: CallbackQuery):
    """Restart VPN server."""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа!", show_alert=True)
        return

    try:
        vpn = VPNManager()
        vpn.restart_server()
        await callback.answer("🔄 Сервер Эстония перезагружен!", show_alert=True)
    except Exception as e:
        logger.error(f"Restart error: {e}")
        await callback.answer("❌ Не удалось перезагрузить сервер.", show_alert=True)


@dp.callback_query(F.data == "admin_users")
async def admin_users(callback: CallbackQuery):
    """Show users list."""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа!", show_alert=True)
        return

    users = db.get_all_users()

    text = f"👥 <b>Всего пользователей: {len(users)}</b>\n\n"
    text += "Последние 10:\n"

    for user in users[-10:]:
        username = user[1] if user[1] else "Нет username"
        text += f"• @{username} (ID: <code>{user[0]}</code>)\n"

    await callback.message.edit_text(text, reply_markup=admin_menu(), parse_mode=ParseMode.HTML)


@dp.callback_query(F.data == "admin_keys")
async def admin_keys(callback: CallbackQuery):
    """Show all active keys."""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа!", show_alert=True)
        return

    db.cursor.execute("SELECT COUNT(*) FROM vpn_keys WHERE is_active = 1")
    count = db.cursor.fetchone()[0]

    await callback.message.edit_text(
        f"🔑 <b>Активных ключей: {count}</b>\n\n"
        f"📊 В базе данных: {count} ключей",
        reply_markup=admin_menu(),
        parse_mode=ParseMode.HTML
    )


@dp.message(Command("block"))
async def block_user_cmd(message: Message):
    """Block user by admin. Usage: /block USER_ID"""
    if not is_admin(message.from_user.id):
        await message.answer("❌ У тебя нет доступа!")
        return

    args = message.text.split()
    if len(args) != 2:
        await message.answer("❌ Использование: <code>/block USER_ID</code>", parse_mode=ParseMode.HTML)
        return

    try:
        user_id = int(args[1])
        db.block_user(user_id)

        # Remove user from Estonia server
        try:
            vpn = VPNManager()
            keys = db.cursor.execute("SELECT uuid FROM vpn_keys WHERE user_id = ?", (user_id,)).fetchall()
            for key in keys:
                vpn.remove_key_from_all_servers(key[0])
        except Exception as e:
            logger.error(f"Error removing user from server: {e}")

        await message.answer(
            f"✅ Пользователь <code>{user_id}</code> заблокирован и удалён с сервера.",
            parse_mode=ParseMode.HTML
        )
    except ValueError:
        await message.answer("❌ USER_ID должен быть числом!")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


@dp.message(Command("unblock"))
async def unblock_user_cmd(message: Message):
    """Unblock user by admin. Usage: /unblock USER_ID"""
    if not is_admin(message.from_user.id):
        await message.answer("❌ У тебя нет доступа!")
        return

    args = message.text.split()
    if len(args) != 2:
        await message.answer("❌ Использование: <code>/unblock USER_ID</code>", parse_mode=ParseMode.HTML)
        return

    try:
        user_id = int(args[1])
        db.unblock_user(user_id)
        await message.answer(f"✅ Пользователь <code>{user_id}</code> разблокирован.", parse_mode=ParseMode.HTML)
    except ValueError:
        await message.answer("❌ USER_ID должен быть числом!")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


@dp.message(Command("blocked"))
async def list_blocked_cmd(message: Message):
    """List blocked users."""
    if not is_admin(message.from_user.id):
        await message.answer("❌ У тебя нет доступа!")
        return

    blocked = db.get_blocked_users()

    if not blocked:
        await message.answer("✅ Нет заблокированных пользователей.")
        return

    text = f"🚫 <b>Заблокированные пользователи ({len(blocked)}):</b>\n\n"
    for user in blocked:
        username = user[1] if user[1] else "Нет username"
        text += f"• ID: <code>{user[0]}</code> | @{username}\n"

    await message.answer(text, parse_mode=ParseMode.HTML)


@dp.message(Command("ref"))
async def referral_cmd(message: Message):
    """Show referral link and stats."""
    user_id = message.from_user.id

    ref_link = generate_referral_link(user_id, BOT_USERNAME)
    balance_info = db.get_user_balance(user_id)
    referral_count = db.get_referral_count(user_id)

    text = (
        f"🎁 <b>Реферальная программа</b>\n"
        f"{DIV}\n"
        f"🔗 <b>Твоя ссылка:</b>\n"
        f"<code>{ref_link}</code>\n"
        f"{DIV}\n"
        f"📊 <b>Статистика:</b>\n"
        f"👥 Приглашено: <b>{referral_count}</b>\n"
        f"⏰ Бонусные часы: <b>+{balance_info['bonus_hours']}ч</b>\n"
        f"💰 Баланс: <b>{balance_info['balance']}₽</b>\n"
        f"{DIV}\n"
        f"🎁 <b>Награды:</b>\n"
        f"• +6 часов VPN за каждого друга\n"
        f"• +2% с каждой покупки реферала\n\n"
        f"📤 Поделись ссылкой с друзьями!"
    )

    await message.answer(text, parse_mode=ParseMode.HTML)


@dp.message(Command("getsticker"))
async def getsticker_hint(message: Message):
    """Подсказка как получить file_id стикера."""
    await message.answer(
        "🆔 <b>Получение file_id стикера</b>\n\n"
        "Просто отправь мне любой стикер — я пришлю его file_id.\n"
        "Затем вставь его в <code>config.py → STICKERS</code>.",
        parse_mode=ParseMode.HTML
    )


# ==================== BROADCAST ====================

@dp.message(Command("all"))
async def broadcast_cmd(message: Message):
    """Broadcast message to all users. Usage: /all message"""
    if not is_admin(message.from_user.id):
        await message.answer("❌ У тебя нет доступа!")
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("❌ Использование: <code>/all текст сообщения</code>", parse_mode=ParseMode.HTML)
        return

    broadcast_text = args[1]
    user_ids = db.get_all_user_ids()

    sent = 0
    failed = 0

    status_msg = await message.answer(f"📢 Рассылка начата...\n👥 Получателей: {len(user_ids)}")

    for user_id in user_ids:
        try:
            await bot.send_message(
                user_id,
                f"📢 <b>Сообщение от администрации:</b>\n\n{broadcast_text}",
                parse_mode=ParseMode.HTML
            )
            sent += 1
        except Exception as e:
            logger.error(f"Failed to send broadcast to {user_id}: {e}")
            failed += 1
        await asyncio.sleep(0.05)  # Rate limit protection

    await status_msg.edit_text(
        f"✅ <b>Рассылка завершена!</b>\n\n"
        f"📤 Отправлено: {sent}\n"
        f"❌ Ошибок: {failed}",
        parse_mode=ParseMode.HTML
    )


@dp.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_callback(callback: CallbackQuery):
    """Prompt admin to use /all command."""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа!", show_alert=True)
        return

    await callback.message.edit_text(
        f"📢 <b>Массовая рассылка</b>\n\n"
        f"Используй команду:\n"
        f"<code>/all текст сообщения</code>\n\n"
        f"Пример:\n"
        f"<code>/all Привет всем! Новые цены на VPN!</code>",
        reply_markup=admin_menu(),
        parse_mode=ParseMode.HTML
    )


# ==================== STICKER FILE_ID GRABBER ====================

@dp.message(F.sticker)
async def grab_sticker_id(message: Message):
    """При получении стикера присылает его file_id — удобно для настройки STICKERS."""
    sticker = message.sticker
    is_premium = getattr(sticker, "is_premium", None) or bool(getattr(sticker, "premium_animation", None))
    kind = "🎬 анимированный" if sticker.is_animated else ("📹 видео" if sticker.is_video else "🖼 статичный")
    await message.answer(
        f"🆔 <b>file_id стикера:</b>\n"
        f"<code>{sticker.file_id}</code>\n\n"
        f"Тип: {kind}{' · ⭐️ premium' if is_premium else ''}\n\n"
        f"Скопируй и вставь в <code>config.py → STICKERS</code>.",
        parse_mode=ParseMode.HTML
    )


# ==================== EXPIRED KEYS CLEANUP ====================

async def cleanup_expired_keys():
    """Background task to remove expired keys from servers."""
    while True:
        try:
            await asyncio.sleep(600)  # Check every 10 minutes
            expired_keys = db.get_expired_keys()
            if expired_keys:
                logger.info(f"Found {len(expired_keys)} expired keys to cleanup")
                for key in expired_keys:
                    try:
                        key_id = key[0]
                        client_uuid = key[2]
                        user_id = key[1]
                        vpn_manager = VPNManager()
                        vpn_manager.remove_key_from_all_servers(client_uuid)
                        db.deactivate_key(key_id)
                        logger.info(f"Deactivated expired key {key_id} for user {user_id}")
                    except Exception as exc:
                        logger.error(f"Error cleaning up key: {exc}")
        except Exception as exc:
            logger.error(f"Cleanup task error: {exc}")
            await asyncio.sleep(60)


# ==================== MAIN ====================

async def main():
    """Start the bot."""
    logger.info(f"Starting {VPN_NAME} bot...")
    asyncio.create_task(cleanup_expired_keys())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
