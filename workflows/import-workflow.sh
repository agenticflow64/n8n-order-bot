#!/usr/bin/env bash
# Импорт workflow в запущенный n8n (docker compose) + активация.
# Идемпотентен: в order-bot.json задан фиксированный id, поэтому повторный
# импорт обновляет workflow на месте (upsert), не создавая копий.
#
# Использование: ./workflows/import-workflow.sh
set -euo pipefail
cd "$(dirname "$0")/.."

WORKFLOW_FILE="/import/order-bot.json"
WORKFLOW_NAME="Order Bot — приём заказов (TG + эмулятор)"
WORKFLOW_ID="1759000000001"

echo "==> n8n: импорт $WORKFLOW_FILE (upsert id=$WORKFLOW_ID)"
docker compose exec -T n8n n8n import:workflow --input="$WORKFLOW_FILE"

echo "==> n8n: активация workflow id=$WORKFLOW_ID"
docker compose exec -T n8n n8n update:workflow --id="$WORKFLOW_ID" --active=true 2>&1 | grep -v "deprecated\|Please use\|Publishing\|^$\|take effect" || true

echo "==> n8n: рестарт, чтобы активация и вебхук вступили в силу"
docker compose restart n8n >/dev/null
until curl -sf -m 3 http://localhost:5678/healthz >/dev/null 2>&1; do sleep 2; done

echo ""
echo "Готово. Workflow активен:"
echo "  UI:       http://localhost:5678 (workflow «$WORKFLOW_NAME»)"
echo "  Webhook:  http://localhost:5678/webhook/order-bot"
echo "  Эмулятор: http://localhost:8000/chat"
