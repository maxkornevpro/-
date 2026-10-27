#!/usr/bin/env python3
"""
server_setup.py — установка/обновление AeroProjectVPN ПРЯМО НА СЕРВЕРЕ.

Запускать НА сервере Эстония от root, из папки с ботом:
    python3 server_setup.py

Без paramiko, без паролей, без SSH-из-вне — всё локально. Нужен только python3.
Делает: убивает старый бот -> ставит зависимости -> создаёт systemd-сервисы
(bot/sub/webapp) -> запускает -> печатает статус и nginx-сниппет.
"""

import os
import subprocess
import sys
import time

BOT_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON = sys.executable
WEBAPP_PORT = 9090
WEBAPP_PATH = "/tgapp/"

SERVICES = {
    "aeroprojectvpn-bot": "bot.py",
    "aeroprojectvpn-sub": "subscription_api.py",
    "aeroprojectvpn-webapp": "webapp_api.py",
}


def sh(cmd, show=True):
    if show:
        print("  $", cmd)
    return subprocess.run(cmd, shell=True).returncode


def out(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout.strip()


def unit(name, script):
    return f"""[Unit]
Description=AeroProjectVPN {name}
After=network.target

[Service]
Type=simple
WorkingDirectory={BOT_DIR}
ExecStart={PYTHON} {BOT_DIR}/{script}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""


def kill_old():
    print("\n🛑 Убиваю старый бот (если есть)...")
    sh(
        r'''for u in $(grep -rilE "bot\.py|subscription_api|webapp_api|aiogram|aeroprojectvpn|vpn_bot|telebot" /etc/systemd/system/ 2>/dev/null); do '''
        r'''n=$(basename "$u"); systemctl stop "$n" 2>/dev/null; systemctl disable "$n" 2>/dev/null; '''
        r'''case "$n" in aeroprojectvpn-bot.service|aeroprojectvpn-sub.service|aeroprojectvpn-webapp.service) ;; *) rm -f "$u";; esac; '''
        r'''done; systemctl daemon-reload 2>/dev/null; true''',
        show=False,
    )
    sh("command -v pm2 >/dev/null 2>&1 && pm2 delete all >/dev/null 2>&1; "
       "pkill -9 -f 'SCREEN.*bot' 2>/dev/null; "
       "pkill -9 -f 'bot\\.py' 2>/dev/null; pkill -9 -f subscription_api 2>/dev/null; "
       "pkill -9 -f webapp_api 2>/dev/null; true", show=False)
    time.sleep(2)
    left = out("ps -eo args | grep -iE 'python.*(bot\\.py|subscription_api|webapp_api|aiogram)' | grep -v grep | wc -l")
    print(f"  ✅ Осталось bot-процессов: {left or '0'}")


def install_deps():
    print("\n📦 Ставлю зависимости...")
    req = os.path.join(BOT_DIR, "requirements.txt")
    base = [PYTHON, "-m", "pip", "install"]
    for extra in ([], ["--break-system-packages"], ["--user"]):
        if subprocess.run(base + extra + ["-r", req]).returncode == 0:
            print("  ✅ Зависимости готовы")
            return
    sys.exit("❌ Не удалось поставить зависимости")


def setup_services():
    print("\n⚙️  Создаю systemd-сервисы...")
    for name, script in SERVICES.items():
        with open(f"/etc/systemd/system/{name}.service", "w", encoding="utf-8") as f:
            f.write(unit(name, script))
    sh("systemctl daemon-reload")
    sh(f"systemctl enable {' '.join(SERVICES)}", show=False)
    sh(f"systemctl restart {' '.join(SERVICES)}")
    time.sleep(5)


def status():
    print("\n📊 Статус:")
    ok = True
    for name in SERVICES:
        st = out(f"systemctl is-active {name}")
        icon = "🟢" if st == "active" else "🔴"
        print(f"  {icon} {name}: {st}")
        if st != "active":
            ok = False
            sh(f"journalctl -u {name} -n 15 --no-pager")
    bot_cnt = out("pgrep -f bot.py | wc -l")
    print(f"  🔢 Процессов bot.py: {bot_cnt or '0'} (должно быть 1)")
    return ok


def main():
    if hasattr(os, "geteuid") and os.geteuid() != 0:
        sys.exit("❌ Запусти от root:  sudo python3 server_setup.py")
    if not os.path.isfile(os.path.join(BOT_DIR, "bot.py")):
        sys.exit(f"❌ Рядом нет bot.py ({BOT_DIR}). Запускай из папки с ботом.")

    print("🚀 Установка AeroProjectVPN на этом сервере")
    print("=" * 50)
    kill_old()
    install_deps()
    setup_services()
    ok = status()

    print("\n" + "=" * 50)
    print("✅ ГОТОВО!" if ok else "⚠️ Что-то не поднялось — смотри логи выше.")
    print(f"""
🔧 Отдать Mini App по HTTPS — добавь в nginx (внутри 443-блока домена):

    location {WEBAPP_PATH} {{
        proxy_pass http://127.0.0.1:{WEBAPP_PORT}/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }}

Затем:  nginx -t && systemctl reload nginx
""")


if __name__ == "__main__":
    main()
