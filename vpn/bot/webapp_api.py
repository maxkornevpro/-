#!/usr/bin/env python3
"""
webapp_api.py — бэкенд Telegram Mini App (aiohttp).

Отдаёт статику Mini App (webapp/) и JSON-API. Каждый запрос аутентифицируется
по Telegram WebApp initData (см. services.validate_init_data) — клиенту не верим.

Зависимости: aiohttp (идёт вместе с aiogram) + aiocryptopay (для крипто-оплаты).
Запуск: python3 webapp_api.py  (слушает 0.0.0.0:WEBAPP_PORT, проксируется nginx'ом).
"""

from __future__ import annotations

import asyncio
import functools
import os

from aiohttp import web

from config import (
    ADMIN_IDS,
    ADMIN_USERNAME,
    CRYPTO_BOT_TOKEN,
    PRICES,
    TRIAL_DAYS,
    VPN_NAME,
    WEBAPP_PORT,
)
from database import Database
import services
from services import (
    PLAN_DAYS,
    PLAN_TITLE,
    build_state,
    build_subscription_state,
    is_admin,
    issue_key,
    tg_send_message,
    validate_init_data,
)

db = Database()
WEBAPP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "webapp")

_cp = None


def get_cryptopay():
    global _cp
    if _cp is None and CRYPTO_BOT_TOKEN:
        from aiocryptopay import AioCryptoPay, Networks
        _cp = AioCryptoPay(token=CRYPTO_BOT_TOKEN, network=Networks.MAIN_NET)
    return _cp


def auth_user(request):
    """Достать и проверить пользователя из initData. None если невалидно."""
    init_data = request.headers.get("X-Init-Data", "")
    data = validate_init_data(init_data)
    if not data or not data.get("user"):
        return None
    return data["user"]


def err(message, status=400):
    return web.json_response({"ok": False, "error": message}, status=status)


async def run_blocking(func, *args):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, functools.partial(func, *args))


# ==================== API ====================

async def api_state(request):
    user = auth_user(request)
    if not user:
        return err("Не удалось подтвердить личность. Откройте приложение из Telegram.", 401)
    return web.json_response(build_state(db, user))


async def api_trial(request):
    user = auth_user(request)
    if not user:
        return err("auth", 401)
    uid = int(user["id"])

    if db.is_user_blocked(uid):
        return err("Аккаунт заблокирован")
    if db.has_used_trial(uid):
        return err("Пробный период уже был использован")
    if db.get_active_subscription(uid):
        return err("У вас уже есть активная подписка")

    db.set_trial_used(uid)
    try:
        await run_blocking(issue_key, db, uid, TRIAL_DAYS)
    except Exception:
        return err("Сервер сейчас недоступен, попробуйте через минуту", 503)

    db.add_subscription(uid, "trial", 0, TRIAL_DAYS)
    return web.json_response({"ok": True, "subscription": build_subscription_state(db, uid)})


async def api_buy(request):
    user = auth_user(request)
    if not user:
        return err("auth", 401)
    uid = int(user["id"])
    username = user.get("username")

    try:
        body = await request.json()
    except Exception:
        body = {}
    plan = body.get("plan")
    method = body.get("method")

    price = PRICES.get(plan)
    if not price:
        return err("Неизвестный тариф")

    title = PLAN_TITLE.get(plan, plan)

    if method == "crypto":
        cp = get_cryptopay()
        if not cp:
            return err("Крипто-оплата временно недоступна")
        try:
            invoice = await cp.create_invoice(
                amount=price, fiat="RUB", currency_type="fiat",
                description=f"{VPN_NAME} — {title}",
            )
        except Exception:
            return err("Не удалось создать счёт, попробуйте позже", 503)
        order_id = db.create_order(uid, username, plan, price, invoice.invoice_id)
        return web.json_response({
            "ok": True, "method": "crypto",
            "pay_url": invoice.bot_invoice_url, "order_id": order_id,
        })

    if method in ("card_ru", "card_ua"):
        order_id = db.create_order(uid, username, plan, price)
        kb = {"inline_keyboard": [[
            {"text": "✅ Подтвердить", "callback_data": f"confirm_pay_{order_id}"},
            {"text": "❌ Отклонить", "callback_data": f"reject_pay_{order_id}"},
        ]]}
        flag = "🇷🇺" if method == "card_ru" else "🇺🇦"
        text = (
            f"🛒 <b>Новый заказ (карта {flag})</b>\n"
            f"👤 @{username or uid}  (<code>{uid}</code>)\n"
            f"📦 {title} — {price}₽\n"
            f"📋 Order #{order_id}\n\n"
            f"❗️ Ожидает подтверждения"
        )
        for admin_id in ADMIN_IDS:
            tg_send_message(admin_id, text, kb)
        card = services.CARD_RU if method == "card_ru" else services.CARD_UA
        return web.json_response({
            "ok": True, "method": method, "order_id": order_id,
            "card": card, "admin": ADMIN_USERNAME,
        })

    return err("Неизвестный способ оплаты")


async def api_payment_status(request):
    user = auth_user(request)
    if not user:
        return err("auth", 401)
    uid = int(user["id"])

    try:
        body = await request.json()
    except Exception:
        body = {}
    order_id = body.get("order_id")
    if not order_id:
        return err("Нет номера заказа")

    db.cursor.execute("SELECT * FROM orders WHERE id = ? AND user_id = ?", (order_id, uid))
    order = db.cursor.fetchone()
    if not order:
        return err("Заказ не найден", 404)

    if order[5] == "paid":
        return web.json_response({"ok": True, "status": "paid",
                                  "subscription": build_subscription_state(db, uid)})

    invoice_id = order[8]
    if not invoice_id:
        return web.json_response({"ok": True, "status": "pending"})

    cp = get_cryptopay()
    if not cp:
        return web.json_response({"ok": True, "status": "pending"})
    try:
        invoices = await cp.get_invoices(invoice_ids=invoice_id)
    except Exception:
        return web.json_response({"ok": True, "status": "pending"})

    if invoices and invoices[0].status == "paid":
        await _grant_paid_order(order)
        return web.json_response({"ok": True, "status": "paid",
                                  "subscription": build_subscription_state(db, uid)})

    return web.json_response({"ok": True, "status": "pending"})


async def _grant_paid_order(order):
    """Отметить заказ оплаченным, начислить кэшбэк рефереру и выдать ключ."""
    order_id, uid, _username, plan, price = order[0], order[1], order[2], order[3], order[4]
    days = PLAN_DAYS.get(plan, 30)

    db.mark_order_paid(order_id)
    db.add_subscription(uid, plan, price, days)

    user_row = db.get_user(uid)
    if user_row and user_row[6]:  # referrer_id
        cashback = db.add_purchase_cashback(user_row[6], price)
        tg_send_message(user_row[6],
                        f"🎉 Реферальный кэшбэк: <b>+{cashback}₽</b> на баланс!")

    await run_blocking(issue_key, db, uid, days)
    tg_send_message(uid, f"✅ Оплата получена! Подписка <b>{PLAN_TITLE.get(plan, plan)}</b> активна 🇪🇪")


async def api_renew(request):
    user = auth_user(request)
    if not user:
        return err("auth", 401)
    uid = int(user["id"])

    sub = db.get_active_subscription(uid)
    if not sub:
        return err("Нет активной подписки")
    plan = sub[4]
    days = TRIAL_DAYS if plan == "trial" else PLAN_DAYS.get(plan, 30)

    try:
        await run_blocking(issue_key, db, uid, days)
    except Exception:
        return err("Сервер недоступен, попробуйте позже", 503)

    return web.json_response({"ok": True, "subscription": build_subscription_state(db, uid)})


# ==================== ADMIN ====================

def admin_only(request):
    user = auth_user(request)
    if not user:
        return None, err("auth", 401)
    if not is_admin(int(user["id"])):
        return None, err("Нет доступа", 403)
    return user, None


async def api_admin_stats(request):
    user, error = admin_only(request)
    if error:
        return error
    stats = db.get_stats()
    pending = len(db.get_pending_orders())
    return web.json_response({"ok": True, "stats": {**stats, "pending_orders": pending}})


async def api_admin_users(request):
    user, error = admin_only(request)
    if error:
        return error
    users = db.get_all_users()[:60]
    return web.json_response({"ok": True, "users": [
        {"id": u[0], "username": u[1], "first_name": u[2],
         "joined": str(u[3]) if len(u) > 3 else None,
         "blocked": (len(u) > 5 and u[5] == 0)}
        for u in users
    ]})


async def api_admin_orders(request):
    user, error = admin_only(request)
    if error:
        return error
    orders = db.get_pending_orders()
    return web.json_response({"ok": True, "orders": [
        {"id": o[0], "user_id": o[1], "username": o[2],
         "plan": PLAN_TITLE.get(o[3], o[3]), "price": o[4], "created": str(o[6])}
        for o in orders
    ]})


async def api_admin_order_action(request):
    user, error = admin_only(request)
    if error:
        return error
    try:
        body = await request.json()
    except Exception:
        body = {}
    order_id = body.get("order_id")
    action = body.get("action")

    db.cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
    order = db.cursor.fetchone()
    if not order or order[5] != "pending":
        return err("Заказ не найден или уже обработан")

    if action == "confirm":
        await _grant_paid_order(order)
        return web.json_response({"ok": True})
    if action == "reject":
        db.cursor.execute("UPDATE orders SET status = 'rejected' WHERE id = ?", (order_id,))
        db.conn.commit()
        tg_send_message(order[1], f"❌ Заказ #{order_id} отклонён. Свяжитесь с {ADMIN_USERNAME}")
        return web.json_response({"ok": True})
    return err("Неизвестное действие")


async def api_admin_broadcast(request):
    user, error = admin_only(request)
    if error:
        return error
    try:
        body = await request.json()
    except Exception:
        body = {}
    text = (body.get("text") or "").strip()
    if not text:
        return err("Пустой текст")

    user_ids = db.get_all_user_ids()

    def _send_all():
        sent = 0
        for uid in user_ids:
            res = tg_send_message(uid, f"📢 <b>Сообщение от администрации</b>\n\n{text}")
            if res and res.get("ok"):
                sent += 1
        return sent

    sent = await run_blocking(_send_all)
    return web.json_response({"ok": True, "sent": sent, "total": len(user_ids)})


# ==================== СТАТИКА ====================

def _file(name):
    async def handler(request):
        return web.FileResponse(os.path.join(WEBAPP_DIR, name))
    return handler


def create_app():
    app = web.Application()
    app.router.add_get("/", _file("index.html"))
    app.router.add_get("/index.html", _file("index.html"))
    app.router.add_get("/style.css", _file("style.css"))
    app.router.add_get("/app.js", _file("app.js"))

    app.router.add_post("/api/state", api_state)
    app.router.add_post("/api/trial", api_trial)
    app.router.add_post("/api/buy", api_buy)
    app.router.add_post("/api/payment-status", api_payment_status)
    app.router.add_post("/api/renew", api_renew)
    app.router.add_post("/api/admin/stats", api_admin_stats)
    app.router.add_post("/api/admin/users", api_admin_users)
    app.router.add_post("/api/admin/orders", api_admin_orders)
    app.router.add_post("/api/admin/order-action", api_admin_order_action)
    app.router.add_post("/api/admin/broadcast", api_admin_broadcast)
    return app


if __name__ == "__main__":
    print(f"🌐 {VPN_NAME} Mini App backend on :{WEBAPP_PORT}")
    web.run_app(create_app(), host="0.0.0.0", port=WEBAPP_PORT)
