#!/usr/bin/env python3
"""
AeroProjectVPN — одна команда для полного деплоя на сервер Эстония.

    python run.py          # убить старый бот + залить новый + запустить ВСЁ
    python run.py all       # то же самое (полный деплой)
    python run.py kill      # только убить старый бот на сервере (без деплоя)

Скрипт сам ставит paramiko (нужен для SSH). Пароль уже зашит в
vpn/bot/deploy_estonia.py — вводить ничего не надо.
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOT_DIR = os.path.join(HERE, "vpn", "bot")


def ensure_paramiko():
    try:
        import paramiko  # noqa: F401
        return
    except ImportError:
        pass
    print("📦 Ставлю paramiko (нужен для SSH)...")
    base = [sys.executable, "-m", "pip", "install"]
    for extra in ([], ["--break-system-packages"], ["--user"]):
        if subprocess.call(base + extra + ["paramiko"]) == 0:
            return
    sys.exit("❌ Не удалось поставить paramiko. Поставь вручную: pip install paramiko")


def main():
    arg = sys.argv[1].lower() if len(sys.argv) > 1 else "deploy"
    if arg == "all":
        arg = "deploy"
    if arg not in ("deploy", "kill"):
        sys.exit("Использование: python run.py [all|deploy|kill]")

    if not os.path.isfile(os.path.join(BOT_DIR, "deploy_estonia.py")):
        sys.exit("❌ Не найден vpn/bot/deploy_estonia.py.\n"
                 "Запускай из корня репозитория на ветке 'new'.")

    ensure_paramiko()

    cmd = [sys.executable, "deploy_estonia.py"]
    if arg == "kill":
        cmd.append("kill")
    sys.exit(subprocess.call(cmd, cwd=BOT_DIR))


if __name__ == "__main__":
    main()
