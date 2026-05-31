# AeroProjectVPN — бот + Mini App

Чистая ветка `release` с актуальным ботом и нормальным запуском через systemd.
Всё разворачивается **прямо на сервере** (через SSH/Termius), без обёрток и SFTP.

## Состав
- `bot.py` — Telegram-бот (aiogram), лаунчер Mini App
- `webapp_api.py` — бэкенд Mini App (aiohttp), порт **9090**
- `subscription_api.py` — выдача подписок/конфигов
- `webapp/` — сам Mini App (`index.html`, `style.css`, `app.js`)
- `services.py`, `database.py`, `vpn_manager.py`, `panel_3xui.py`, `token_crypto.py`, `config.py`
- `setup.sh` — установка/запуск на сервере (venv + 3 systemd-сервиса)
- `update.sh` — обновление (git pull + перезапуск)

Сервисы systemd: `aeroprojectvpn-bot`, `aeroprojectvpn-sub`, `aeroprojectvpn-webapp`.

## Первая установка на сервере (Termius, от root)

```bash
mkdir -p /opt/aeroprojectvpn
cd /opt/aeroprojectvpn
git clone -b release https://github.com/maxkornevpro/-.git bot
cd bot
sudo bash setup.sh
```

## Если бот уже стоит в `/opt/aeroprojectvpn/bot` (миграция без потери базы)

```bash
systemctl stop aeroprojectvpn-bot aeroprojectvpn-sub aeroprojectvpn-webapp 2>/dev/null
cd /opt/aeroprojectvpn/bot
cp -a vpn_bot.db /root/vpn_bot.db.bak 2>/dev/null || true   # бэкап базы
git init -q
git remote add origin https://github.com/maxkornevpro/-.git 2>/dev/null \
  || git remote set-url origin https://github.com/maxkornevpro/-.git
git fetch origin release
git reset --hard origin/release
git clean -fd -e vpn_bot.db                                  # убрать старые лишние файлы, базу сохранить
sudo bash setup.sh
```

## Обновление (после новых коммитов в `release`)

```bash
cd /opt/aeroprojectvpn/bot
sudo bash update.sh
```

## Полезное

```bash
# логи бота в реальном времени
journalctl -u aeroprojectvpn-bot -f
# статус всех сервисов
systemctl status aeroprojectvpn-bot aeroprojectvpn-sub aeroprojectvpn-webapp
```

> Приватный репозиторий: для `git clone/fetch` нужен доступ — SSH-ключ
> (`git@github.com:maxkornevpro/-.git`) или Personal Access Token в HTTPS-URL.
