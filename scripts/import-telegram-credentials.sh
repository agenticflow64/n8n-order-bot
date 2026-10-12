#!/usr/bin/env bash
# Импорт Telegram Bot API credential в запущенный n8n (docker compose).
# Токен берётся из .env (TELEGRAM_BOT_TOKEN) и в git/логи не попадает:
# JSON с токеном пишется прямо в контейнер во временный файл и удаляется.
#
# Идемпотентен: фиксированный id "telegram-order-bot", повторный импорт
# обновляет токен на месте (upsert). Workflow ссылается на этот id.
set -euo pipefail
cd "$(dirname "$0")/.."

set -a; source .env; set +a
if [[ -z "${TELEGRAM_BOT_TOKEN:-}" ]]; then
  echo "TELEGRAM_BOT_TOKEN не задан в .env — пропускаю импорт credential (TG-опрос будет неактивен)."
  exit 0
fi

CRED_ID="telegram-order-bot"
CRED_NAME="Telegram Bot (order-bot)"

echo "==> n8n: импорт Telegram credential (id=$CRED_ID, токен не выводится)"
docker compose exec -T n8n sh -c "cat > /tmp/tg-cred.json && n8n import:credentials --input=/tmp/tg-cred.json && rm -f /tmp/tg-cred.json" <<EOF
[{"id": "$CRED_ID", "name": "$CRED_NAME", "type": "telegramApi", "data": {"accessToken": "$TELEGRAM_BOT_TOKEN", "baseUrl": "https://api.telegram.org"}}]
EOF

echo "==> Готово. Credential «$CRED_NAME» доступен в n8n."
