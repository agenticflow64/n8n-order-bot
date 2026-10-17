# n8n-order-bot

Приём заказов в свободной форме через Telegram-бота: **n8n** оркестрирует флоу, **LLM (OpenRouter, бесплатные модели)** приводит текст к структуре, **FastAPI-backend** хранит заказы и отдаёт админку, клиенту в чат уходит подтверждение с человекочитаемой сводкой.

Портфолио-кейс: [freelans-way/portfolio/case-n8n-order-bot](../portfolio/case-n8n-order-bot/README.md).

## Задача → Решение → Результат

**Задача.** Клиенты пишут заказы «как попало»: с опечатками, капсом, «срочно!!», без части данных. Ручной разбор таких сообщений занимает время и допускает ошибки.

**Решение.** Конвейер на n8n: сообщение (Telegram или веб-эмулятор) → LLM извлекает `service_type / fields / urgency / customer_name / contact / valid` строгим JSON → валидация и Switch → заказ в backend (pydantic, дедуп по хэшу текста, статусы) → подтверждение клиенту. Невалидное — ретрай и ветка «оператор подключится вручную».

**Результат (демо-замеры, модель `liquid/lfm-2.5-2.6b:free`, 12 сэмплов из `docs/sample-orders.md`).**
Актуальные цифры — в README кейса; воспроизвести: `python3 scripts/measure_accuracy.py`.

## Стек

- **n8n** — оркестрация, LLM вызывается HTTP Request-нодой (ключ из env контейнера, не из credentials)
- **OpenRouter** — только бесплатные модели (`:free`); выбор модели — ниже
- **Python / FastAPI / SQLAlchemy / SQLite** — backend
- **docker compose** — n8n + backend, healthchecks
- **pytest** — API/e2e тесты (LLL замокан) + смоук с реальным API (`-m smoke`)

## Выбор модели (замер на 12 сэмплах, реальный API)

| Модель (`:free`) | Все поля верно | Медиана ответа | Вывод |
|---|---|---|---|
| **liquid/lfm-2.5-2.6b** ← выбрана | 7/12 (58%) | 4.5 с | валидность 12/12, услуги 10/12; телефон добирается регэкспом из сырого текста |
| nvidia/nemotron-3.5-lightning | 12/12 (100%) | 17.2 с | лучшая точность, но на 2026-10 деградировала до ~40 с — не для живого демо |
| nvidia/nemotron-3-super-120b-a12b | — | 11–25 с | точная и стабильная, но медленнее интервала опроса TG |
| nvidia/nemotron-3-ultra-550b-a55b | 10/12 (83%) | 9.4 с | быстрая альтернатива, 2 сбоя API за прогон |
| google/gemma-4-31b-it | 1/12 (429 на 11) | — | жёсткий rate-limit upstream — отклонена |
| poolside/laguna-s-2.1 | 2/12 (429 на 10) | — | rate-limit — отклонена |

Поменять модель можно одной переменной `OPENROUTER_MODEL` в `.env`. Замоканные тесты от модели не зависят; телефон достаётся детерминированно регэкспом из исходного текста (LLM иногда искажает цифры), резерв после LLM — ретраи и эскалация оператору. Дубли ответов при параллельном опросе отсекаются: backend дедуплицирует заказ по хэшу текста, workflow не отправляет второе сообщение по флагу `duplicate`.

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
| Эмулятор Telegram-чата (второй канал демо) | http://localhost:8000/chat |
| Админка заказов | http://localhost:8000 |
| Webhook n8n | `POST http://localhost:5678/webhook/order-bot` |

Первый вход в n8n попросит создать локального владельца (owner) — это нормально для локального демо.

## Реальный Telegram-бот (polling)

Локальный n8n сидит за NAT без публичного URL, поэтому встроенный «Telegram Trigger» (он работает только через webhook) не подходит. Вместо него в workflow стоит цепочка getUpdates-опроса: «TG: расписание опроса» (каждые 30 с) → «TG: смещение (offset)» → «TG: getUpdates» (long poll 25 с) → «TG: новые сообщения» (offset хранится в static data воркфлоу, поэтому повторный опрос не обрабатывает одно сообщение дважды).

Настройка после `docker compose up -d --build`:

1. Заполните `TELEGRAM_BOT_TOKEN` в `.env` (токен от @BotFather) и пересоздайте n8n: `docker compose up -d n8n`.
2. Запустите `./workflows/import-workflow.sh` — скрипт импортирует credential `Telegram Bot (order-bot)` (токен берётся из `.env`, в логи и git не попадает), обновит workflow и активирует его.

Для живой проверки напишите боту **/start** — придёт приветствие с примерами заказов (без LLM, мгновенно). Затем заказ текстом, например: «надо стрижку собаке на выходные, телефон 89161234567». Ответ придёт в тот же чат через ноду «Ответ клиенту (Telegram)» с inline-кнопками «✓ Подтвердить» / «✗ Отменить»: нажатие попадает в тот же getUpdates-опрос, меняет статус заказа в backend (`/orders/{id}/confirm` или `/orders/{id}/cancel`), после чего бот убирает кнопки и правит текст сообщения («Заказ №N подтверждён, ждите звонка» / «Заказ №N отменён»). Задержка до ~30 с — это интервал опроса; выполнение видно в n8n UI → Executions (каждые 30 с там появляются опросы, включая пустые).

Без токена в `.env` цепочка опроса сама выключается (нода «TG: смещение» возвращает пусто), стек работает только на веб-эмуляторе.

## Веб-эмулятор чата (демо без Telegram)

Эмулятор `http://localhost:8000/chat` отправляет те же данные, что и реальный бот, в ноду «Webhook: Эмулятор чата» (`POST /webhook/order-bot`, body `{"text": "...", "name": "Клиент", "source": "emulator"}`), и получает ответ через `Respond to Webhook`.

Тестовый режим ноды: в n8n нажмите «Listen for test event» на Webhook-ноде и в эмуляторе («Настройки») замените URL на `http://localhost:5678/webhook-test/order-bot` — удобно, чтобы видеть выполнение именно в открытом редакторе.

## Архитектура

Подробно, с mermaid-диаграммой и описанием каждой ноды: [docs/architecture.md](docs/architecture.md).

- **Дедупликация**: sha256 нормализованного текста (регистр/пробелы), повтор → `200 duplicate: true`, новый заказ не создаётся.
- **Ретрай**: невалидный JSON/услуга → пауза 3 с → повторный вызов LLM → при второй неудаче заказ «Ручная обработка» + сообщение про оператора.
- **Приветствие**: `/start` и `/help` перехватываются до LLM (нода «Приветствие или заказ?»), текст — копия `backend/app/bot_replies.py`.
- **Inline-кнопки**: подтверждение заказа в Telegram — кнопки `confirm:{id}` / `cancel:{id}`; нажатия обрабатывает ветка «Кнопка: …» (backend → answerCallbackQuery → editMessageText). Тексты и логика — `backend/app/bot_replies.py`, покрыты pytest.
- **Статусы**: `new → confirmed → in_progress → done`, `cancelled` (у подтверждённого заказа `confirmed_at`; отмена — `POST /orders/{id}/cancel`, выполненный заказ отменить нельзя).
- **Секреты**: только через `.env` (git-ignored) и переменные окружения контейнеров; в workflow JSON и в git ключей нет.

## Тесты

```bash
backend/.venv/bin/python -m pytest          # API + e2e (LLL замокан): 23 passed
backend/.venv/bin/python -m pytest -m smoke # смоук с реальным OpenRouter API
```

Покрыто: pydantic-валидация, дедуп, статусы/подтверждение/отмена, фильтры админ-API, e2e (структурированный заказ в БД + сгенерированное подтверждение), эскалация мусорных сообщений, приветствие и обработка inline-кнопок (юнит-тесты логики Code-нод), реальный LLM-смоук.

## Структура

```
workflows/order-bot.json     # n8n workflow (импорт: ./workflows/import-workflow.sh)
scripts/import-telegram-credentials.sh  # credential Telegram Bot API в n8n (токен из .env)
backend/app/                 # FastAPI: main, schemas, models, prompt, confirmations
backend/app/static/          # админка (/) и эмулятор чата (/chat)
backend/tests/               # pytest: test_api, test_e2e, test_smoke_llm
scripts/                     # samples.json + measure_accuracy.py (реальные замеры)
docs/                        # architecture.md, demo-script.md, sample-orders.md
```
