#!/usr/bin/env bash
# Импорт workflow в запущенный n8n (docker compose) + активация.
# Идемпотентен: старые копии с тем же именем удаляются перед импортом.
#
# Использование: ./workflows/import-workflow.sh
set -euo pipefail
cd "$(dirname "$0")/.."

WORKFLOW_FILE="/import/order-bot.json"
WORKFLOW_NAME="Order Bot — приём заказов (TG + эмулятор)"

echo "==> n8n: удаляем предыдущие копии workflow (если были)"
IDS=$(docker compose exec -T n8n n8n export:workflow --all 2>/dev/null | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    data = []
for wf in data:
    if wf.get('name') == '$WORKFLOW_NAME':
        print(wf.get('id'))
" || true)
for id in $IDS; do
  echo "    удаляем старую копию id=$id"
  docker compose exec -T n8n n8n delete:workflow --id="$id" >/dev/null
done

echo "==> n8n: импорт $WORKFLOW_FILE"
docker compose exec -T n8n n8n import:workflow --input="$WORKFLOW_FILE"

echo "==> n8n: ищем id импортированного workflow"
NEW_ID=$(docker compose exec -T n8n n8n export:workflow --all 2>/dev/null | python3 -c "
import json, sys
data = json.load(sys.stdin)
for wf in data:
    if wf.get('name') == '$WORKFLOW_NAME':
        print(wf.get('id'))
        break
")
if [ -z "$NEW_ID" ]; then
  echo "ОШИБКА: workflow не найден после импорта" >&2
  exit 1
fi

echo "==> n8n: активация workflow id=$NEW_ID"
docker compose exec -T n8n n8n update:workflow --id="$NEW_ID" --active=true

echo ""
echo "Готово. Workflow активен:"
echo "  UI:       http://localhost:5678 (workflow «$WORKFLOW_NAME»)"
echo "  Webhook:  http://localhost:5678/webhook/order-bot"
echo "  Эмулятор: http://localhost:8000/chat"
