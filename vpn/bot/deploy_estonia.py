#!/usr/bin/env python3
"""
Деплой AeroProjectVPN (бот + Mini App) на сервер Эстония.

Что делает скрипт:
  1. Подключается к серверу Эстония по SSH.
  2. ОСТАНАВЛИВАЕТ любой старый бот/API (systemd, nohup, screen).
  3. Загружает файлы бота, Mini App-бэкенд и статику Mini App.
  4. Ставит зависимости (aiogram, aiohttp, paramiko, requests, aiocryptopay).
  5. Создаёт 3 systemd-сервиса (автозапуск + авторестарт):
       - aeroprojectvpn-bot.service       (Telegram-бот-лаунчер)
       - aeroprojectvpn-sub.service        (Subscription API, :8080)
       - aeroprojectvpn-webapp.service     (Mini App бэкенд, :8090)
  6. Перезапускает, проверяет статус и печатает nginx-сниппет для Mini App.

Запуск с машины с доступом в интернет:
    pip install paramiko
    python3 deploy_estonia.py
"""

import os
import sys
import time

import paramiko

# ==================== СЕРВЕР ЭСТОНИЯ ====================
HOST = "95.85.249.79"
USER = "root"
PASSWORD = "FNvhSI1r4VVdbj7G"
SSH_PORT = 22

REMOTE_DIR = "/opt/aeroprojectvpn/bot"
PYTHON = "/usr/bin/python3"
WEBAPP_PORT = 8090
WEBAPP_PATH = "/tgapp/"  # путь, по которому nginx отдаёт Mini App

LOCAL_DIR = os.path.dirname(os.path.abspath(__file__))

PY_FILES = [
    "bot.py", "config.py", "database.py", "vpn_manager.py", "panel_3xui.py",
    "subscription_api.py", "token_crypto.py", "services.py", "webapp_api.py",
    "requirements.txt",
]
WEBAPP_FILES = ["webapp/index.html", "webapp/style.css", "webapp/app.js"]


def service_unit(desc, exec_target):
    return f"""[Unit]
Description={desc}
After=network.target

[Service]
Type=simple
WorkingDirectory={REMOTE_DIR}
ExecStart={PYTHON} {REMOTE_DIR}/{exec_target}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""


SERVICES = {
    "aeroprojectvpn-bot": service_unit("AeroProjectVPN Telegram Bot", "bot.py"),
    "aeroprojectvpn-sub": service_unit("AeroProjectVPN Subscription API", "subscription_api.py"),
    "aeroprojectvpn-webapp": service_unit("AeroProjectVPN Mini App backend", "webapp_api.py"),
}


def run(client, cmd, timeout=600, show=True):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    code = stdout.channel.recv_exit_status()
    out = stdout.read().decode(errors="ignore").strip()
    err = stderr.read().decode(errors="ignore").strip()
    if show and out:
        print(out)
    if show and err and code != 0:
        print(f"  ⚠️ {err[:500]}")
    return code, out


def write_remote_file(client, path, content):
    run(client, f"cat > {path} << 'AERO_EOF'\n{content}\nAERO_EOF", show=False)


def stop_old_instances(client):
    print("\n🛑 Останавливаю старые экземпляры...")
    run(
        client,
        r'''
for unit in $(grep -rlE "bot\.py|subscription_api|webapp_api" /etc/systemd/system/ 2>/dev/null); do
    name=$(basename "$unit")
    echo "  • systemd: $name -> stop + disable"
    systemctl stop "$name" 2>/dev/null
    systemctl disable "$name" 2>/dev/null
    case "$name" in
        aeroprojectvpn-bot.service|aeroprojectvpn-sub.service|aeroprojectvpn-webapp.service) ;;
        *) rm -f "$unit" ;;
    esac
done
systemctl daemon-reload 2>/dev/null
true
''',
    )
    run(client, "pkill -9 -f bot.py 2>/dev/null; pkill -9 -f subscription_api 2>/dev/null; "
                "pkill -9 -f webapp_api 2>/dev/null; true", show=False)
    time.sleep(2)
    _, cnt = run(client, "ps aux | grep -E 'bot\\.py|subscription_api|webapp_api' | grep -v grep | wc -l", show=False)
    print(f"  ✅ Старое остановлено. Процессов: {cnt or '0'}")


def main():
    missing = [f for f in PY_FILES + WEBAPP_FILES if not os.path.isfile(os.path.join(LOCAL_DIR, f))]
    if missing:
        print(f"❌ Не найдены файлы: {missing}")
        sys.exit(1)

    print(f"🚀 Деплой AeroProjectVPN (бот + Mini App) на Эстонию ({HOST})")
    print("=" * 56)

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print("🔌 Подключаюсь по SSH...")
    client.connect(HOST, port=SSH_PORT, username=USER, password=PASSWORD, timeout=30)
    print("✅ Подключено")

    stop_old_instances(client)

    print(f"\n📁 Готовлю {REMOTE_DIR}...")
    run(client, f"mkdir -p {REMOTE_DIR}/webapp")

    print("\n📤 Загружаю файлы...")
    sftp = client.open_sftp()
    for filename in PY_FILES + WEBAPP_FILES:
        try:
            sftp.put(os.path.join(LOCAL_DIR, filename), f"{REMOTE_DIR}/{filename}")
            print(f"  ✅ {filename}")
        except Exception as exc:
            print(f"  ❌ {filename}: {exc}")
    sftp.close()

    print("\n📦 Ставлю зависимости (пару минут)...")
    run(client, f"{PYTHON} -m pip install --break-system-packages --upgrade "
                f"aiogram aiohttp paramiko requests aiocryptopay 2>&1 | tail -3")

    print("\n🧪 Проверка синтаксиса на сервере...")
    code, out = run(
        client,
        f"cd {REMOTE_DIR} && {PYTHON} -m py_compile bot.py config.py database.py vpn_manager.py "
        f"panel_3xui.py subscription_api.py token_crypto.py services.py webapp_api.py && echo SYNTAX_OK",
    )
    if "SYNTAX_OK" not in out:
        print("❌ Ошибка синтаксиса. Сервисы не трогаю.")
        client.close()
        sys.exit(1)
    print("✅ Синтаксис в порядке")

    print("\n⚙️  Создаю systemd-сервисы...")
    for name, unit in SERVICES.items():
        write_remote_file(client, f"/etc/systemd/system/{name}.service", unit)
    run(client, "systemctl daemon-reload")
    run(client, f"systemctl enable {' '.join(SERVICES)}", show=False)

    print("\n🔄 Запускаю сервисы...")
    run(client, f"systemctl restart {' '.join(SERVICES)}")
    time.sleep(5)

    print("\n📊 Статус:")
    all_ok = True
    for name in SERVICES:
        _, status = run(client, f"systemctl is-active {name}", show=False)
        icon = "🟢" if status == "active" else "🔴"
        print(f"  {icon} {name}: {status}")
        if status != "active":
            all_ok = False
            run(client, f"journalctl -u {name} -n 15 --no-pager")

    _, bot_cnt = run(client, "pgrep -f bot.py | wc -l", show=False)
    print(f"  🔢 Процессов bot.py: {bot_cnt or '0'} (должно быть 1)")

    client.close()

    print("\n" + "=" * 56)
    if all_ok:
        print("✅ ГОТОВО! Бот, API и Mini App запущены.")
    else:
        print("⚠️ Какой-то сервис не активен — смотри логи выше.")

    print(f"""
🔧 ОСТАЛОСЬ ОДНО: отдать Mini App по HTTPS через nginx.
Добавь в server-блок домена ee.aeroproject.fun (внутри 443) этот location:

    location {WEBAPP_PATH} {{
        proxy_pass http://127.0.0.1:{WEBAPP_PORT}/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }}

Затем:  nginx -t && systemctl reload nginx

После этого Mini App доступен по: https://ee.aeroproject.fun{WEBAPP_PATH}
(этот же URL уже прописан в config.WEBAPP_URL — бот откроет его сам).

Проверка: открой бота, /start → «Открыть приложение».
""")


if __name__ == "__main__":
    main()
