#!/usr/bin/env python3
"""
AeroProjectVPN — локальный запуск (GitHub Codespaces / любой компьютер).

Чистый Python, только стандартная библиотека. Никакого SSH, paramiko и паролей.
Сам ставит нужные зависимости и поднимает сервисы.

Запуск:
    python run.py            # поставить зависимости и запустить ВСЁ (бот + webapp + sub)
    python run.py bot        # только Telegram-бот
    python run.py webapp     # только Mini App backend (порт 9090)
    python run.py sub        # только Subscription API (порт 8080)
    python run.py deps       # только установить зависимости
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOT_DIR = os.path.join(HERE, "vpn", "bot")

# Зависимости для локального запуска. paramiko НЕ нужен — SSH тут не используется,
# ключи выдаются через 3x-ui панель по HTTP.
RUNTIME_DEPS = ["aiogram>=3.0.0", "aiohttp>=3.9.0", "aiocryptopay>=0.4.8", "requests>=2.31.0"]
CHECK_MODULES = ["aiogram", "aiohttp", "aiocryptopay", "requests"]

SERVICES = {
    "webapp": "webapp_api.py",
    "sub": "subscription_api.py",
    "bot": "bot.py",
}


def deps_present():
    for module in CHECK_MODULES:
        try:
            __import__(module)
        except ImportError:
            return False
    return True


def install_deps():
    print("📦 Ставлю зависимости (без paramiko)...")
    base = [sys.executable, "-m", "pip", "install"]
    # Пробуем по очереди: обычно -> --break-system-packages -> --user
    for extra in ([], ["--break-system-packages"], ["--user"]):
        cmd = base + extra + RUNTIME_DEPS
        print("   $ " + " ".join(cmd))
        if subprocess.call(cmd) == 0:
            print("✅ Зависимости готовы.")
            return
    sys.exit("❌ Не удалось установить зависимости. Установи вручную:\n"
             "   pip install " + " ".join(RUNTIME_DEPS))


def run(target):
    names = list(SERVICES) if target == "all" else [target]
    procs = []
    try:
        for name in names:
            script = SERVICES[name]
            print(f"▶️  Запускаю {script}")
            procs.append(subprocess.Popen([sys.executable, script], cwd=BOT_DIR))
        print("\n🚀 Работает. Нажми Ctrl+C, чтобы остановить.\n")
        for proc in procs:
            proc.wait()
    except KeyboardInterrupt:
        print("\n🛑 Останавливаю...")
    finally:
        for proc in procs:
            if proc.poll() is None:
                proc.terminate()
        for proc in procs:
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "all"
    if target not in ("all", "bot", "webapp", "sub", "deps"):
        sys.exit("Использование: python run.py [all|bot|webapp|sub|deps]")

    if not os.path.isdir(BOT_DIR):
        sys.exit(f"❌ Не найдена папка с ботом: {BOT_DIR}\n"
                 "Запускай из корня репозитория и убедись, что ты на ветке 'new'.")

    if target == "deps":
        install_deps()
        return

    if not deps_present():
        install_deps()

    run(target)


if __name__ == "__main__":
    main()
