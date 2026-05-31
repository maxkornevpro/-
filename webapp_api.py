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
import time
from collections import defaultdict, deque

from aiohttp import web

from config import (
    ADMIN_IDS,
    ADMIN_USERNAME,
    CRYPTO_BOT_TOKEN,
    DEVICE_PACK_PRICE,
    DEVICE_PACK_SIZE,
    PRICES,
    TRIAL_DAYS,
    VPN_NAME,
    WEBAPP_PORT,
)
from database import Database
import services
from services import (
    DEVICES_PLAN,
    PLAN_DAYS,
    PLAN_TITLE,
    apply_device_limit,
    build_devices_state,
    build_state,
    build_subscription_state,
    extend_or_issue_key,
    is_admin,
    is_devices_plan,
    issue_key,
    tg_send_message,
    validate_init_data,
)

db = Database()
WEBAPP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "webapp")
WEBAPP_PREFIX = "/tgapp"

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

    # Докупка устройств — отдельный «товар» с фикс. ценой, не из PRICES.
    if is_devices_plan(plan):
        plan = DEVICES_PLAN
        price = DEVICE_PACK_PRICE
    else:
        price = PRICES.get(plan)
        # Подписку нельзя купить повторно, пока активна и осталось больше 1 дня.
        sub_state = build_subscription_state(db, uid)
        if not services.can_buy_subscription(sub_state):
            if sub_state.get("forever"):
                return err("У вас бессрочная подписка — продлевать не нужно.")
            dl = sub_state.get("days_left")
            return err(
                f"Продлить можно, когда останется 1 день или меньше. "
                f"Сейчас осталось {dl} дн."
            )
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
            {"text": "Подтвердить", "callback_data": f"confirm_pay_{order_id}"},
            {"text": "Отклонить", "callback_data": f"reject_pay_{order_id}"},
        ]]}
        region = "РФ" if method == "card_ru" else "Украина"
        text = (
            f"<b>Новый заказ — карта ({region})</b>\n"
            f"Пользователь: @{username or uid} (<code>{uid}</code>)\n"
            f"Тариф: {title} — {price}₽\n"
            f"Заказ #{order_id} · ожидает подтверждения"
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
    """Отметить заказ оплаченным, начислить кэшбэк рефереру и выдать товар."""
    order_id, uid, _username, plan, price = order[0], order[1], order[2], order[3], order[4]

    db.mark_order_paid(order_id)

    user_row = db.get_user(uid)
    if user_row and user_row[6]:  # referrer_id
        cashback = db.add_purchase_cashback(user_row[6], price)
        tg_send_message(user_row[6],
                        f"Реферальный бонус: <b>+{cashback}₽</b> на баланс.")

    # Докупка устройств: увеличиваем лимит и применяем к активному ключу.
    if is_devices_plan(plan):
        new_limit = db.add_device_slots(uid, DEVICE_PACK_SIZE)
        await run_blocking(apply_device_limit, db, uid)
        tg_send_message(uid, f"Оплата получена. Лимит устройств теперь <b>{new_limit}</b>.")
        return

    days = PLAN_DAYS.get(plan, 30)
    db.add_subscription(uid, plan, price, days)
    # Продлеваем срок активного ключа (или выдаём новый, если ключа ещё нет),
    # а не перевыпускаем — иначе оплаченные дни «не доходят» до пользователя.
    await run_blocking(extend_or_issue_key, db, uid, days)
    tg_send_message(uid, f"Оплата получена. Подписка <b>{PLAN_TITLE.get(plan, plan)}</b> активна.")


async def api_devices(request):
    """Живой статус устройств (обращается к 3x-ui)."""
    user = auth_user(request)
    if not user:
        return err("auth", 401)
    uid = int(user["id"])
    state = await run_blocking(build_devices_state, db, uid)
    return web.json_response({"ok": True, "devices": state})


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
        await run_blocking(extend_or_issue_key, db, uid, days)
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
        tg_send_message(order[1], f"Заказ #{order_id} отклонён. Свяжитесь с {ADMIN_USERNAME}")
        return web.json_response({"ok": True})
    return err("Неизвестное действие")


async def api_admin_user(request):
    """Найти пользователя по ID или @username и вернуть детальную карточку."""
    user, error = admin_only(request)
    if error:
        return error
    try:
        body = await request.json()
    except Exception:
        body = {}
    q = (body.get("query") or "").strip()
    if not q:
        return err("Введите ID или @username")

    q2 = q.lstrip("@")
    if q.startswith("@") or not q2.isdigit():
        row = db.get_user_by_username(q2)
    else:
        row = db.get_user(int(q2))

    if not row:
        return err("Пользователь не найден", 404)

    detail = services.build_admin_user_detail(db, row[0])
    return web.json_response({"ok": True, "user": detail})


async def api_admin_user_action(request):
    """Действия над пользователем: блок / разблок / выдать дни подписки."""
    user, error = admin_only(request)
    if error:
        return error
    try:
        body = await request.json()
    except Exception:
        body = {}
    target_id = body.get("user_id")
    action = body.get("action")
    if not target_id:
        return err("Не указан пользователь")
    target_id = int(target_id)

    if not db.get_user(target_id):
        return err("Пользователь не найден", 404)

    if action == "block":
        db.block_user(target_id)
        tg_send_message(target_id, "Доступ к VPN приостановлен администратором.")
    elif action == "unblock":
        db.unblock_user(target_id)
        tg_send_message(target_id, "Доступ к VPN снова открыт.")
    elif action == "grant":
        try:
            days = int(body.get("days") or 0)
        except (TypeError, ValueError):
            days = 0
        if days <= 0 or days > 3650:
            return err("Укажите число дней от 1 до 3650")
        db.add_subscription(target_id, "grant", 0, days)
        try:
            await run_blocking(extend_or_issue_key, db, target_id, days)
        except Exception:
            return err("Не удалось обновить ключ на сервере, попробуйте позже", 503)
        tg_send_message(
            target_id,
            f"Вам начислено <b>{days}</b> дн. подписки. Откройте приложение, чтобы подключиться.",
        )
    else:
        return err("Неизвестное действие")

    detail = services.build_admin_user_detail(db, target_id)
    return web.json_response({"ok": True, "user": detail})


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
            res = tg_send_message(uid, f"<b>Сообщение от администрации</b>\n\n{text}")
            if res and res.get("ok"):
                sent += 1
        return sent

    sent = await run_blocking(_send_all)
    return web.json_response({"ok": True, "sent": sent, "total": len(user_ids)})


# ==================== БЕЗОПАСНОСТЬ (rate-limit + заголовки) ====================

# Лимиты «запросов за окно (сек)» по типам путей. Память — в процессе
# (webapp_api один процесс), чего достаточно против накрутки и перебора.
_RL_BUCKETS = defaultdict(deque)


def _client_ip(request):
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()
    return request.headers.get("X-Real-IP") or (request.remote or "?")


def _rl_rule(path):
    if path.startswith("/api/admin/"):
        return ("admin", 40, 60)
    if path in ("/api/trial", "/api/buy", "/api/payment-status", "/api/renew"):
        return ("sensitive", 20, 60)
    if path.startswith("/api/"):
        return ("api", 120, 60)
    return None


@web.middleware
async def rate_limit_mw(request, handler):
    rule = _rl_rule(request.path)
    if rule:
        bucket, limit, window = rule
        key = (_client_ip(request), bucket)
        now = time.monotonic()
        dq = _RL_BUCKETS[key]
        while dq and now - dq[0] > window:
            dq.popleft()
        if len(dq) >= limit:
            return web.json_response(
                {"ok": False, "error": "Слишком много запросов, попробуйте позже"},
                status=429,
            )
        dq.append(now)
        if len(_RL_BUCKETS) > 5000:      # защита от роста словаря
            _RL_BUCKETS.clear()
    return await handler(request)


def _apply_security_headers(resp, request):
    h = resp.headers
    h["X-Content-Type-Options"] = "nosniff"
    h["Referrer-Policy"] = "no-referrer"
    h["X-Robots-Tag"] = "noindex, nofollow"
    # Mini App открывается внутри Telegram (в т.ч. в iframe на web.telegram.org).
    h["Content-Security-Policy"] = "frame-ancestors https://web.telegram.org https://*.telegram.org"
    h["Server"] = "aeroproject"
    if request.path.startswith("/api/"):
        h["Cache-Control"] = "no-store"


@web.middleware
async def security_headers_mw(request, handler):
    try:
        resp = await handler(request)
    except web.HTTPException as ex:
        _apply_security_headers(ex, request)
        raise
    _apply_security_headers(resp, request)
    return resp


# ==================== СТАТИКА ====================

def _file(name):
    async def handler(request):
        return web.FileResponse(os.path.join(WEBAPP_DIR, name))
    return handler


def _register(app, method, path, handler):
    app.router.add_route(method, path, handler)
    if path == "/":
        app.router.add_route(method, WEBAPP_PREFIX + "/", handler)
    elif path == "/tgapp":
        return
    else:
        app.router.add_route(method, WEBAPP_PREFIX + path, handler)


def redirect_tgapp(request):
    raise web.HTTPMovedPermanently(location=WEBAPP_PREFIX + "/")


def create_app():
    app = web.Application(middlewares=[security_headers_mw, rate_limit_mw])
    _register(app, "GET", "/", _file("index.html"))
    _register(app, "GET", "/index.html", _file("index.html"))
    _register(app, "GET", "/style.css", _file("style.css"))
    _register(app, "GET", "/app.js", _file("app.js"))
    _register(app, "GET", "/tgapp", redirect_tgapp)

    _register(app, "POST", "/api/state", api_state)
    _register(app, "POST", "/api/trial", api_trial)
    _register(app, "POST", "/api/buy", api_buy)
    _register(app, "POST", "/api/payment-status", api_payment_status)
    _register(app, "POST", "/api/devices", api_devices)
    _register(app, "POST", "/api/renew", api_renew)
    _register(app, "POST", "/api/admin/stats", api_admin_stats)
    _register(app, "POST", "/api/admin/users", api_admin_users)
    _register(app, "POST", "/api/admin/orders", api_admin_orders)
    _register(app, "POST", "/api/admin/order-action", api_admin_order_action)
    _register(app, "POST", "/api/admin/user", api_admin_user)
    _register(app, "POST", "/api/admin/user-action", api_admin_user_action)
    _register(app, "POST", "/api/admin/broadcast", api_admin_broadcast)
    return app


if __name__ == "__main__":
    print(f"{VPN_NAME} Mini App backend on :{WEBAPP_PORT}")
    web.run_app(create_app(), host="0.0.0.0", port=WEBAPP_PORT)
