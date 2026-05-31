#!/usr/bin/env python3
"""
AeroProjectVPN — тонкий бот-лаунчер для Mini App.

Вся логика и красивый интерфейс живут в Mini App (webapp/ + webapp_api.py).
Бот делает немного, но важное:
  - /start: реферальная привязка, проверка подписки на канал, кнопка «Открыть приложение»;
  - кнопка-меню чата открывает Mini App;
  - подтверждение/отклонение оплат картой (приходят админу в чат от webapp_api).
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import (
    BotCommand,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonWebApp,
    Message,
    WebAppInfo,
)

from config import (
    ADMIN_IDS,
    ADMIN_USERNAME,
    BOT_TOKEN,
    CHANNEL_ID,
    CHANNEL_REQUIRED,
    CHANNEL_USERNAME,
    DEVICE_PACK_SIZE,
    VPN_NAME,
    WEBAPP_URL,
)
from database import Database
from services import (
    PLAN_DAYS,
    PLAN_TITLE,
    apply_device_limit,
    extend_or_issue_key,
    is_devices_plan,
    issue_key,
)
from token_crypto import decrypt_token

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
db = Database()

WELCOME = (
    f"<b>{VPN_NAME}</b>\n\n"
    "Быстрый VPN на сервере в Эстонии. Без логов, без рекламы, "
    "без ограничений по трафику.\n\n"
    "Первый день — бесплатно, карта не нужна. Нажмите кнопку ниже, "
    "чтобы открыть приложение."
)


def open_app_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Открыть приложение", web_app=WebAppInfo(url=WEBAPP_URL)),
    ]])


def subscribe_kb() -> InlineKeyboardMarkup:
    channel = CHANNEL_USERNAME.lstrip("@")
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Подписаться на канал", url=f"https://t.me/{channel}")],
        [InlineKeyboardButton(text="Я подписался", callback_data="check_sub")],
    ])


async def is_subscribed(user_id: int) -> bool:
    if not CHANNEL_REQUIRED:
        return True
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ("member", "administrator", "creator")
    except Exception:
        return True  # не блокируем из-за сбоя проверки


@dp.message(CommandStart())
async def cmd_start(message: Message):
    uid = message.from_user.id

    # Реферал из /start ref_<token>
    referrer_id = None
    if message.text and len(message.text.split()) > 1:
        param = message.text.split()[1]
        if param.startswith("ref_"):
            referrer_id = decrypt_token(param[4:])
            if referrer_id == uid:
                referrer_id = None

    db.add_user(uid, message.from_user.username, message.from_user.first_name, referrer_id)

    if db.is_user_blocked(uid):
        await message.answer(f"Доступ заблокирован. Поддержка: {ADMIN_USERNAME}")
        return

    if not await is_subscribed(uid):
        await message.answer(
            "Чтобы пользоваться ботом, подпишитесь на наш канал.",
            reply_markup=subscribe_kb(),
        )
        return

    await message.answer(WELCOME, reply_markup=open_app_kb(), parse_mode=ParseMode.HTML)


@dp.callback_query(F.data == "check_sub")
async def check_sub(callback: CallbackQuery):
    if await is_subscribed(callback.from_user.id):
        await callback.message.edit_text(WELCOME, reply_markup=open_app_kb(), parse_mode=ParseMode.HTML)
    else:
        await callback.answer("Подписка на канал пока не найдена", show_alert=True)


@dp.callback_query(F.data.startswith("confirm_pay_"))
async def confirm_pay(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Нет доступа", show_alert=True)
        return

    order_id = int(callback.data.rsplit("_", 1)[-1])
    db.cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
    order = db.cursor.fetchone()
    if not order or order[5] != "pending":
        await callback.answer("Заказ уже обработан", show_alert=True)
        return

    uid, plan, price = order[1], order[3], order[4]

    db.mark_order_paid(order_id)

    user_row = db.get_user(uid)
    if user_row and user_row[6]:  # referrer cashback
        cashback = db.add_purchase_cashback(user_row[6], price)
        try:
            await bot.send_message(user_row[6], f"Реферальный бонус: <b>+{cashback}₽</b> на баланс.", parse_mode=ParseMode.HTML)
        except Exception:
            pass

    # Докупка устройств — увеличиваем лимит, ключ не перевыпускаем.
    if is_devices_plan(plan):
        new_limit = db.add_device_slots(uid, DEVICE_PACK_SIZE)
        try:
            await asyncio.to_thread(apply_device_limit, db, uid)
        except Exception as exc:
            logger.error(f"apply_device_limit failed: {exc}")
        try:
            await bot.send_message(
                uid,
                f"Оплата подтверждена. Лимит устройств теперь <b>{new_limit}</b>.",
                reply_markup=open_app_kb(),
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass
        await callback.message.edit_text(f"Заказ #{order_id} подтверждён (+{DEVICE_PACK_SIZE} устройств).")
        return

    days = PLAN_DAYS.get(plan, 30)
    db.add_subscription(uid, plan, price, days)

    try:
        # Продлеваем срок активного ключа (прибавляем дни), а не перевыпускаем —
        # иначе при активном пробном тарифе оплаченные дни «не добавлялись».
        await asyncio.to_thread(extend_or_issue_key, db, uid, days)
    except Exception as exc:
        logger.error(f"extend_or_issue_key failed: {exc}")
        await callback.answer("Ошибка выдачи ключа", show_alert=True)
        return

    try:
        await bot.send_message(
            uid,
            f"Оплата подтверждена. Подписка <b>{PLAN_TITLE.get(plan, plan)}</b> активна.\n"
            "Откройте приложение, чтобы подключиться.",
            reply_markup=open_app_kb(),
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass

    await callback.message.edit_text(f"Заказ #{order_id} подтверждён, ключ выдан.")


@dp.callback_query(F.data.startswith("reject_pay_"))
async def reject_pay(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Нет доступа", show_alert=True)
        return

    order_id = int(callback.data.rsplit("_", 1)[-1])
    db.cursor.execute("SELECT user_id FROM orders WHERE id = ?", (order_id,))
    row = db.cursor.fetchone()
    db.cursor.execute("UPDATE orders SET status = 'rejected' WHERE id = ?", (order_id,))
    db.conn.commit()

    if row:
        try:
            await bot.send_message(row[0], f"Заказ #{order_id} отклонён. Поддержка: {ADMIN_USERNAME}")
        except Exception:
            pass

    await callback.message.edit_text(f"Заказ #{order_id} отклонён.")


async def setup_bot():
    try:
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(text="Открыть VPN", web_app=WebAppInfo(url=WEBAPP_URL))
        )
    except Exception as exc:
        logger.warning(f"Не удалось установить кнопку-меню: {exc}")
    try:
        await bot.set_my_commands([BotCommand(command="start", description="Открыть VPN")])
    except Exception:
        pass


async def main():
    logger.info(f"Starting {VPN_NAME} launcher bot...")
    await setup_bot()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
