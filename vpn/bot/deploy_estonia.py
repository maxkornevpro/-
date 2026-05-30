#!/usr/bin/env python3
"""
Деплой бота AeroProjectVPN на сервер Эстония (единственный сервер).

Что делает скрипт:
  1. Подключается к серверу Эстония по SSH.
  2. Загружает файлы бота в /opt/aeroprojectvpn/bot.
  3. Устанавливает зависимости (aiogram, paramiko, requests, aiocryptopay).
  4. Создаёт systemd-сервисы (автозапуск + авторестарт):
       - aeroprojectvpn-bot.service       (Telegram-бот)
       - aeroprojectvpn-sub.service        (Subscription API на :8080)
  5. Перезапускает сервисы и проверяет статус.

Запуск (с локальной машины, где установлен paramiko):
    pip install paramiko
    python3 deploy_estonia.py

ВАЖНО: запускать нужно из окружения с доступом в интернет (SSH к серверу).
"""

import os
import sys
import time

import paramiko

# ==================== НАСТРОЙКИ СЕРВЕРА ЭСТОНИЯ ====================
HOST = "95.85.249.79"
USER = "root"
PASSWORD = "FNvhSI1r4VVdbj7G"
SSH_PORT = 22

REMOTE_DIR = "/opt/aeroprojectvpn/bot"
PYTHON = "/usr/bin/python3"

# Файлы бота, которые загружаем (берутся из папки рядом со скриптом)
FILES = [
    "bot.py",
    "config.py",
    "database.py",
    "vpn_manager.py",
    "keyboards.py",
    "panel_3xui.py",
    "subscription_api.py",
    "token_crypto.py",
    "requirements.txt",
]

LOCAL_DIR = os.path.dirname(os.path.abspath(__file__))


BOT_SERVICE = f"""[Unit]
Description=AeroProjectVPN Telegram Bot
After=network.target

[Service]
Type=simple
WorkingDirectory={REMOTE_DIR}
ExecStart={PYTHON} {REMOTE_DIR}/bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""

SUB_SERVICE = f"""[Unit]
Description=AeroProjectVPN Subscription API
After=network.target

[Service]
Type=simple
WorkingDirectory={REMOTE_DIR}
ExecStart={PYTHON} {REMOTE_DIR}/subscription_api.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""


def run(client, cmd, timeout=300, show=True):
    """Выполнить команду по SSH и вернуть (exit_code, stdout, stderr)."""
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode(errors="ignore").strip()
    err = stderr.read().decode(errors="ignore").strip()
    if show:
        if out:
            print(out)
        if err and exit_code != 0:
            print(f"  ⚠️ {err[:500]}")
    return exit_code, out, err


def write_remote_file(client, path, content):
    """Записать файл на сервер через heredoc."""
    safe = content.replace("$", r"\$")
    run(client, f"cat > {path} << 'AERO_EOF'\n{content}\nAERO_EOF", show=False)


def main():
    print(f"🚀 Деплой AeroProjectVPN на Эстонию ({HOST})")
    print("=" * 50)

    # Проверяем, что все локальные файлы на месте
    missing = [f for f in FILES if not os.path.isfile(os.path.join(LOCAL_DIR, f))]
    if missing:
        print(f"❌ Не найдены файлы рядом со скриптом: {missing}")
        sys.exit(1)

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print("🔌 Подключаюсь по SSH...")
    client.connect(HOST, port=SSH_PORT, username=USER, password=PASSWORD, timeout=30)
    print("✅ Подключено")

    # 1. Создаём директорию
    print(f"\n📁 Создаю {REMOTE_DIR}...")
    run(client, f"mkdir -p {REMOTE_DIR}")

    # 2. Загружаем файлы
    print("\n📤 Загружаю файлы бота...")
    sftp = client.open_sftp()
    for filename in FILES:
        local_path = os.path.join(LOCAL_DIR, filename)
        remote_path = f"{REMOTE_DIR}/{filename}"
        try:
            sftp.put(local_path, remote_path)
            print(f"  ✅ {filename}")
        except Exception as exc:
            print(f"  ❌ {filename}: {exc}")
    sftp.close()

    # 3. Устанавливаем зависимости
    print("\n📦 Устанавливаю зависимости (может занять пару минут)...")
    run(
        client,
        f"{PYTHON} -m pip install --break-system-packages --upgrade "
        f"aiogram paramiko requests aiocryptopay 2>&1 | tail -3",
        timeout=600,
    )

    # 4. Проверяем синтаксис на сервере
    print("\n🧪 Проверка синтаксиса на сервере...")
    code, out, err = run(
        client,
        f"cd {REMOTE_DIR} && {PYTHON} -m py_compile bot.py config.py database.py "
        f"vpn_manager.py keyboards.py panel_3xui.py subscription_api.py token_crypto.py "
        f"&& echo SYNTAX_OK",
    )
    if "SYNTAX_OK" not in out:
        print("❌ Ошибка синтаксиса на сервере. Останавливаюсь, сервисы не трогаю.")
        client.close()
        sys.exit(1)
    print("✅ Синтаксис в порядке")

    # 5. Создаём systemd-сервисы
    print("\n⚙️  Настраиваю systemd-сервисы...")
    write_remote_file(client, "/etc/systemd/system/aeroprojectvpn-bot.service", BOT_SERVICE)
    write_remote_file(client, "/etc/systemd/system/aeroprojectvpn-sub.service", SUB_SERVICE)
    run(client, "systemctl daemon-reload")
    run(client, "systemctl enable aeroprojectvpn-bot aeroprojectvpn-sub", show=False)

    # 6. Перезапускаем
    print("\n🔄 Перезапускаю сервисы...")
    run(client, "systemctl restart aeroprojectvpn-bot")
    run(client, "systemctl restart aeroprojectvpn-sub")
    time.sleep(4)

    # 7. Проверяем статус
    print("\n📊 Статус сервисов:")
    _, bot_status, _ = run(client, "systemctl is-active aeroprojectvpn-bot", show=False)
    _, sub_status, _ = run(client, "systemctl is-active aeroprojectvpn-sub", show=False)
    print(f"  🤖 Бот:              {bot_status}")
    print(f"  🌐 Subscription API: {sub_status}")

    if bot_status != "active":
        print("\n⚠️ Логи бота (последние строки):")
        run(client, "journalctl -u aeroprojectvpn-bot -n 20 --no-pager")
    if sub_status != "active":
        print("\n⚠️ Логи API (последние строки):")
        run(client, "journalctl -u aeroprojectvpn-sub -n 20 --no-pager")

    client.close()

    print("\n" + "=" * 50)
    if bot_status == "active" and sub_status == "active":
        print("✅ ГОТОВО! Бот и API запущены на Эстонии.")
    else:
        print("⚠️ Деплой завершён, но какой-то сервис не активен — смотри логи выше.")
    print("\nПолезные команды на сервере:")
    print("  systemctl status aeroprojectvpn-bot")
    print("  journalctl -u aeroprojectvpn-bot -f")
    print("  systemctl restart aeroprojectvpn-bot")


if __name__ == "__main__":
    main()
