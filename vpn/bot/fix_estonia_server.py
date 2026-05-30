#!/usr/bin/env python3
"""
fix_estonia_server.py — быстрый фикс на сервере Эстония.

ЧТО ДЕЛАЕТ:
  1. Останавливает ЛЮБОЙ старый экземпляр бота:
       - systemd-сервисы (любые, чей ExecStart запускает bot.py / subscription_api),
       - процессы nohup / запуск вручную / screen.
  2. (Пере)создаёт systemd-сервисы для нового бота и API.
  3. Запускает новый бот + API и проверяет, что работает РОВНО ОДИН экземпляр.

ГДЕ ЗАПУСКАТЬ:
  Прямо НА сервере Эстония (там, куда залит бот), от root:
      python3 /opt/aeroprojectvpn/bot/fix_estonia_server.py

  Зависимостей нет — нужен только python3 (стандартная библиотека).
"""

import os
import subprocess
import sys
import time

# ==================== НАСТРОЙКИ ====================
REMOTE_DIR = "/opt/aeroprojectvpn/bot"   # папка, куда залит бот
PYTHON = "/usr/bin/python3"

BOT_SERVICE_NAME = "aeroprojectvpn-bot"
SUB_SERVICE_NAME = "aeroprojectvpn-sub"

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


def sh(cmd, check=False):
    """Выполнить shell-команду, вернуть (код, stdout)."""
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    out = (res.stdout or "").strip()
    err = (res.stderr or "").strip()
    if out:
        print(out)
    if err and res.returncode != 0:
        print(f"  ⚠️ {err[:400]}")
    if check and res.returncode != 0:
        sys.exit(f"❌ Команда упала: {cmd}")
    return res.returncode, out


def stop_old_instances():
    """Вырубить ЛЮБОЙ старый экземпляр бота."""
    print("\n🛑 Останавливаю старые экземпляры бота...")

    # 1. Стопаем и выключаем все systemd-юниты, что крутят наш бот/API.
    #    Чужие старые юниты удаляем, свои канонические — оставляем (пересоздадим ниже).
    sh(
        r'''
for unit in $(grep -rlE "bot\.py|subscription_api" /etc/systemd/system/ 2>/dev/null); do
    name=$(basename "$unit")
    echo "  • systemd: $name -> stop + disable"
    systemctl stop "$name" 2>/dev/null
    systemctl disable "$name" 2>/dev/null
    if [ "$name" != "''' + BOT_SERVICE_NAME + r'''.service" ] && [ "$name" != "''' + SUB_SERVICE_NAME + r'''.service" ]; then
        rm -f "$unit"
    fi
done
systemctl daemon-reload 2>/dev/null
true
'''
    )

    # 2. Добиваем процессы (nohup / screen / ручной запуск).
    sh("pkill -9 -f bot.py 2>/dev/null; pkill -9 -f subscription_api 2>/dev/null; "
       "pkill -9 -f 'SCREEN.*bot' 2>/dev/null; true")
    time.sleep(2)

    _, cnt = sh("ps aux | grep -E 'bot\\.py|subscription_api' | grep -v grep | wc -l")
    print(f"  ✅ Старое остановлено. Процессов бота сейчас: {cnt or '0'}")


def ensure_services():
    """(Пере)создать systemd-сервисы для нового бота и API."""
    print("\n⚙️  Создаю/обновляю systemd-сервисы...")

    bot_unit = f"/etc/systemd/system/{BOT_SERVICE_NAME}.service"
    sub_unit = f"/etc/systemd/system/{SUB_SERVICE_NAME}.service"
    with open(bot_unit, "w", encoding="utf-8") as f:
        f.write(BOT_SERVICE)
    with open(sub_unit, "w", encoding="utf-8") as f:
        f.write(SUB_SERVICE)

    sh("systemctl daemon-reload")
    sh(f"systemctl enable {BOT_SERVICE_NAME} {SUB_SERVICE_NAME}")


def start_and_verify():
    """Запустить новый бот + API и проверить, что экземпляр один."""
    print("\n🔄 Запускаю новый бот и API...")
    sh(f"systemctl restart {BOT_SERVICE_NAME}")
    sh(f"systemctl restart {SUB_SERVICE_NAME}")
    time.sleep(4)

    print("\n📊 Статус:")
    _, bot_status = sh(f"systemctl is-active {BOT_SERVICE_NAME}")
    _, sub_status = sh(f"systemctl is-active {SUB_SERVICE_NAME}")
    print(f"  🤖 Бот:              {bot_status}")
    print(f"  🌐 Subscription API: {sub_status}")

    _, bot_cnt = sh("pgrep -f bot.py | wc -l")
    _, sub_cnt = sh("pgrep -f subscription_api | wc -l")
    print(f"  🔢 Процессов bot.py: {bot_cnt or '0'} | subscription_api: {sub_cnt or '0'}")

    if (bot_cnt or "0").strip() != "1":
        print("  ⚠️ Процессов bot.py не ровно 1 — проверь: ps aux | grep bot.py")

    # Проверка логов на конфликт getUpdates
    _, conflict = sh(
        f"journalctl -u {BOT_SERVICE_NAME} -n 50 --no-pager 2>/dev/null "
        f"| grep -ci 'Conflict\\|terminated by other'"
    )
    if (conflict or "0").strip() not in ("0", ""):
        print("  ⚠️ В логах есть Conflict getUpdates — где-то ещё работает старый бот "
              "(возможно на ДРУГОМ сервере!).")

    if bot_status != "active":
        print("\n⚠️ Логи бота:")
        sh(f"journalctl -u {BOT_SERVICE_NAME} -n 20 --no-pager")

    return bot_status == "active" and sub_status == "active" and (bot_cnt or "0").strip() == "1"


def main():
    if os.geteuid() != 0:
        sys.exit("❌ Запусти от root (sudo).")

    if not os.path.isfile(os.path.join(REMOTE_DIR, "bot.py")):
        sys.exit(
            f"❌ Не найден {REMOTE_DIR}/bot.py.\n"
            f"   Сначала залей файлы бота (deploy_estonia.py) или поправь REMOTE_DIR в этом скрипте."
        )

    print("🔧 Фикс бота AeroProjectVPN на Эстонии")
    print("=" * 50)

    stop_old_instances()
    ensure_services()
    ok = start_and_verify()

    print("\n" + "=" * 50)
    if ok:
        print("✅ ГОТОВО! Старый бот остановлен, новый запущен (1 экземпляр).")
        print("   Теперь в Telegram нажми /start — появится новое меню.")
    else:
        print("⚠️ Что-то не так — смотри статус/логи выше.")
    print("\nПолезное:")
    print(f"  systemctl status {BOT_SERVICE_NAME}")
    print(f"  journalctl -u {BOT_SERVICE_NAME} -f")


if __name__ == "__main__":
    main()
