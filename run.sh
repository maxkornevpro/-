#!/usr/bin/env bash
# AeroProjectVPN — локальный запуск (GitHub Codespaces / любой Linux).
# Сам ставит зависимости и поднимает сервисы. Зависит только от python3.
#
# Использование:
#   ./run.sh           # поставить зависимости и запустить ВСЁ (бот + webapp + sub)
#   ./run.sh bot       # только Telegram-бот
#   ./run.sh webapp    # только Mini App backend (порт 9090)
#   ./run.sh sub       # только Subscription API (порт 8080)
#   ./run.sh deps      # только установить зависимости

set -uo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT/vpn/bot"

PYTHON="${PYTHON:-python3}"

# ---------- виртуальное окружение (с фолбэком на системный pip) ----------
USE_VENV=1
if [ ! -d ".venv" ]; then
  echo "🔧 Создаю виртуальное окружение (.venv)..."
  "$PYTHON" -m venv .venv 2>/dev/null || USE_VENV=0
fi
if [ "$USE_VENV" = "1" ] && [ -f ".venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
  PY="python"
  PIP="python -m pip"
else
  echo "⚠️  venv недоступен — ставлю зависимости в систему."
  PY="$PYTHON"
  PIP="$PYTHON -m pip"
fi

install_deps() {
  echo "📦 Устанавливаю зависимости из requirements.txt..."
  $PIP install --upgrade pip >/dev/null 2>&1 || true
  if [ "$USE_VENV" = "1" ]; then
    $PIP install -r requirements.txt
  else
    $PIP install --break-system-packages -r requirements.txt 2>/dev/null \
      || $PIP install --user -r requirements.txt
  fi
  echo "✅ Зависимости готовы."
}

TARGET="${1:-all}"

if [ "$TARGET" = "deps" ]; then
  install_deps
  exit 0
fi

# Ставим зависимости только если их ещё нет (повторный запуск — быстрый).
if ! $PY -c "import aiogram, aiohttp, paramiko, aiocryptopay" >/dev/null 2>&1; then
  install_deps
fi

case "$TARGET" in
  bot)
    echo "🤖 Запускаю bot.py"
    exec $PY bot.py
    ;;
  webapp)
    echo "🌐 Запускаю webapp_api.py (порт 9090)"
    exec $PY webapp_api.py
    ;;
  sub)
    echo "🔗 Запускаю subscription_api.py (порт 8080)"
    exec $PY subscription_api.py
    ;;
  all)
    echo "🚀 Запускаю всё: webapp(9090) + sub(8080) + bot. Ctrl+C — остановить всё."
    trap 'echo; echo "🛑 Останавливаю..."; kill 0' EXIT INT TERM
    $PY webapp_api.py &
    $PY subscription_api.py &
    $PY bot.py &
    wait
    ;;
  *)
    echo "Использование: ./run.sh [all|bot|webapp|sub|deps]"
    exit 1
    ;;
esac
