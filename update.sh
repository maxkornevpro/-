#!/usr/bin/env bash
# Быстрое обновление на сервере: подтянуть код из git и перезапустить сервисы.
# База vpn_bot.db не трогается (она в .gitignore).
#   sudo bash update.sh
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "❌ Запусти от root:  sudo bash update.sh"; exit 1; }

BOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$BOT_DIR"

echo "⬇️  git pull..."
git pull --ff-only

# если venv есть — доустановим возможные новые зависимости
if [ -x "$BOT_DIR/.venv/bin/python" ]; then
  "$BOT_DIR/.venv/bin/python" -m pip install -q -r requirements.txt || true
fi

echo "🔄 Перезапуск сервисов..."
systemctl restart aeroprojectvpn-bot aeroprojectvpn-sub aeroprojectvpn-webapp
sleep 2
for s in aeroprojectvpn-bot aeroprojectvpn-sub aeroprojectvpn-webapp; do
  printf "   %-24s %s\n" "$s" "$(systemctl is-active "$s" || true)"
done
echo "✅ Обновлено."
