#!/usr/bin/env bash
# =============================================================================
#  AeroProjectVPN — установка/обновление ПРЯМО НА СЕРВЕРЕ (Эстония).
#  Запускать от root из папки с ботом:
#       sudo bash setup.sh
#
#  Что делает (идемпотентно, можно гонять повторно):
#    1) создаёт venv .venv и ставит зависимости из requirements.txt
#    2) создаёт/обновляет 3 systemd-сервиса (bot, sub, webapp)
#    3) включает автозапуск и (пере)запускает их
#    4) печатает статус и nginx-сниппет для Mini App
#
#  База данных vpn_bot.db лежит рядом и в git не входит — при обновлении НЕ теряется.
# =============================================================================
set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "❌ Запусти от root:  sudo bash setup.sh"; exit 1; }

BOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$BOT_DIR"
[ -f "$BOT_DIR/bot.py" ] || { echo "❌ Рядом нет bot.py ($BOT_DIR)"; exit 1; }
echo "📁 Папка бота: $BOT_DIR"

WEBAPP_PORT=9090
WEBAPP_PATH="/tgapp/"

# ---------- 1. Python окружение (venv, с откатом на системный python) ----------
VENV="$BOT_DIR/.venv"
if python3 -m venv "$VENV" 2>/dev/null; then
  PY="$VENV/bin/python"
elif command -v apt-get >/dev/null 2>&1 && apt-get update -y && \
     apt-get install -y python3-venv python3-pip && python3 -m venv "$VENV"; then
  PY="$VENV/bin/python"
else
  echo "⚠️  venv недоступен — использую системный python3"
  PY="$(command -v python3)"
fi
echo "🐍 Python: $PY"

echo "📦 Ставлю зависимости..."
"$PY" -m pip install --upgrade pip >/dev/null 2>&1 || true
"$PY" -m pip install -r requirements.txt \
  || "$PY" -m pip install --break-system-packages -r requirements.txt

# ---------- 2. systemd-сервисы ----------
echo "⚙️  Настраиваю systemd-сервисы..."
make_unit () {  # $1 = имя сервиса, $2 = скрипт
  cat > "/etc/systemd/system/$1.service" <<UNIT
[Unit]
Description=AeroProjectVPN $1
After=network.target

[Service]
Type=simple
WorkingDirectory=$BOT_DIR
ExecStart=$PY $BOT_DIR/$2
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT
}
make_unit aeroprojectvpn-bot     bot.py
make_unit aeroprojectvpn-sub     subscription_api.py
make_unit aeroprojectvpn-webapp  webapp_api.py

systemctl daemon-reload
systemctl enable  aeroprojectvpn-bot aeroprojectvpn-sub aeroprojectvpn-webapp >/dev/null 2>&1 || true
systemctl restart aeroprojectvpn-bot aeroprojectvpn-sub aeroprojectvpn-webapp
sleep 3

# ---------- 3. Статус ----------
echo ""
echo "📊 Статус сервисов:"
ALL_OK=1
for s in aeroprojectvpn-bot aeroprojectvpn-sub aeroprojectvpn-webapp; do
  st="$(systemctl is-active "$s" || true)"
  [ "$st" = "active" ] && icon="🟢" || { icon="🔴"; ALL_OK=0; }
  printf "   %s %-24s %s\n" "$icon" "$s" "$st"
done

if [ "$ALL_OK" -ne 1 ]; then
  echo ""
  echo "⚠️  Что-то не поднялось. Логи:  journalctl -u aeroprojectvpn-bot -n 30 --no-pager"
fi

cat <<NGINX

✅ Готово.
   Логи в реальном времени:  journalctl -u aeroprojectvpn-bot -f

🔧 Mini App по HTTPS — добавь в nginx внутри 443-блока домена (если ещё не стоит):

   location ${WEBAPP_PATH} {
       proxy_pass http://127.0.0.1:${WEBAPP_PORT}/;
       proxy_set_header Host \$host;
       proxy_set_header X-Real-IP \$remote_addr;
   }

   затем:  nginx -t && systemctl reload nginx
NGINX
