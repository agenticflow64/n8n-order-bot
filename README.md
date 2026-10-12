# n8n-order-bot

Приём заказов в свободной форме через Telegram-бота: **n8n** оркестрирует флоу, **LLM (OpenRouter, бесплатные модели)** приводит текст к структуре, **FastAPI-backend** хранит заказы и отдаёт админку, клиенту в чат уходит подтверждение с человекочитаемой сводкой.

Портфолио-кейс: [freelans-way/portfolio/case-n8n-order-bot](../portfolio/case-n8n-order-bot/README.md).

## Задача → Решение → Результат

**Задача.** Клиенты пишут заказы «как попало»: с опечатками, капсом, «срочно!!», без части данных. Ручной разбор таких сообщений занимает время и допускает ошибки.

**Решение.** Конвейер на n8n: сообщение (Telegram или веб-эмулятор) → LLM извлекает `service_type / fields / urgency / customer_name / contact / valid` строгим JSON → валидация и Switch → заказ в backend (pydantic, дедуп по хэшу текста, статусы) → подтверждение клиенту. Невалидное — ретрай и ветка «оператор подключится вручную».

**Результат (демо-замеры, модель `nvidia/nemotron-3-super-120b-a12b:free`, 12 сэмплов из `docs/sample-orders.md`).**
Актуальные цифры — в README кейса; воспроизвести: `python3 scripts/measure_accuracy.py`.

## Стек

- **n8n** — оркестрация, LLM вызывается HTTP Request-нодой (ключ из env контейнера, не из credentials)
- **OpenRouter** — только бесплатные модели (`:free`), резерв — GLM
- **Python / FastAPI / SQLAlchemy / SQLite** — backend
- **docker compose** — n8n + backend, healthchecks
- **pytest** — API/e2e тесты (LLL замокан) + смоук с реальным API (`-m smoke`)

## Запуск (3 команды)

```bash
cp .env.example .env      # и заполнить OPENROUTER_API_KEY (уже может быть на месте)
docker compose up -d --build
./workflows/import-workflow.sh
```

Открыть:

| Что | URL |
|-----|-----|
| n8n UI (workflow со выполнениями) | http://localhost:5678 |
| Эмулятор Telegram-чата (демо без токена) | http://localhost:8000/chat |
| Админка заказов (тёмная тема) | http://localhost:8000 |
| Webhook n8n | `POST http://localhost:5678/webhook/order-bot` |

Первый вход в n8n попросит создать локального владельца (owner) — это нормально для локального демо.

## Демо без Telegram-токена

В workflow нода **Telegram Trigger выключена** — стек запускается и работает без токена. Веб-эмулятор `http://localhost:8000/chat` отправляет те же данные, что и реальный бот, в ноду «Webhook: Эмулятор чата» (`POST /webhook/order-bot`, body `{"text": "...", "name": "Клиент", "source": "emulator"}`), и получает ответ через `Respond to Webhook`.

Тестовый режим ноды: в n8n нажмите «Listen for test event» на Webhook-ноде и в эмуляторе (⚙️) замените URL на `http://localhost:5678/webhook-test/order-bot` — удобно, чтобы видеть выполнение именно в открытом редакторе.

## Реальный Telegram-бот

1. Заполните `TELEGRAM_BOT_TOKEN` в `.env` (токен от @BotFather).
2. В n8n UI откройте workflow → нода **Telegram Trigger** → создайте Telegram API credential с этим токеном → **включите ноду**.
3. Пишите боту в Telegram — далее тот же флоу; ответ уйдёт через ноду «Ответ клиенту (Telegram)».

## Архитектура

Подробно, с mermaid-диаграммой и описанием каждой ноды: [docs/architecture.md](docs/architecture.md).

- **Дедупликация**: sha256 нормализованного текста (регистр/пробелы), повтор → `200 duplicate: true`, новый заказ не создаётся.
- **Ретрай**: невалидный JSON/услуга → пауза 3 с → повторный вызов LLM → при второй неудаче заказ «Ручная обработка» + сообщение про оператора.
- **Статусы**: `new → confirmed → in_progress → done`, `cancelled` (у подтверждённого заказа `confirmed_at`).
- **Секреты**: только через `.env` (git-ignored) и переменные окружения контейнеров; в workflow JSON и в git ключей нет.

## Тесты

```bash
backend/.venv/bin/python -m pytest          # API + e2e (LLL замокан): 14 passed
backend/.venv/bin/python -m pytest -m smoke # смоук с реальным OpenRouter API
```

Покрыто: pydantic-валидация, дедуп, статусы/подтверждение, фильтры админ-API, e2e (структурированный заказ в БД + сгенерированное подтверждение), эскалация мусорных сообщений, реальный LLM-смоук.

## Структура

```
workflows/order-bot.json     # n8n workflow (импорт: ./workflows/import-workflow.sh)
backend/app/                 # FastAPI: main, schemas, models, prompt, confirmations
backend/app/static/          # админка (/) и эмулятор чата (/chat)
backend/tests/               # pytest: test_api, test_e2e, test_smoke_llm
scripts/                     # samples.json + measure_accuracy.py (реальные замеры)
docs/                        # architecture.md, demo-script.md, sample-orders.md
```
