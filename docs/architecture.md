# Архитектура

## Общая схема

```mermaid
flowchart LR
    subgraph Клиент
        TG["Telegram-чат\n(реальный бот)"]
        EMU["Веб-эмулятор чата\nlocalhost:8000/chat"]
    end

    subgraph n8n["n8n (localhost:5678) — workflow order-bot"]
        direction TB
        W["Webhook: Эмулятор чата\nPOST /webhook/order-bot"]
        PT["TG: расписание опроса\nкаждые 30 с"]
        PGU["TG: getUpdates\nlong poll 25 с, offset в static data"]
        T["Telegram Trigger\n(webhook-режим, выключен:\nнужен публичный URL)"]
        N["Нормализация ввода\n+ system-промпт"]
        L["LLM: Извлечь заказ\nHTTP → OpenRouter :free"]
        P["Разбор ответа LLM\nJSON + валидация"]
        SW1{"Заказ распознан?"}
        RW["Ретрай: пауза 3 сек"]
        ESC["Эскалация оператору\nPOST /orders (Ручная обработка)"]
        CR["Создать заказ\nPOST backend /orders"]
        FM["Финальное сообщение\nчеловекочитаемая сводка"]
        SW2{"Telegram или эмулятор?"}
        R["Ответ в эмулятор\nRespond to Webhook"]
        TS["Ответ клиенту\nTelegram sendMessage"]
    end

    subgraph Backend["FastAPI backend (localhost:8000)"]
        API["POST /orders\nвалидация pydantic + дедуп по хэшу"]
        ADM["GET /orders, PATCH, /confirm\nадмин-API + SQLite"]
        UI["Админка /\nи эмулятор /chat (static)"]
        DB[(SQLite orders.db)]
    end

    TG --> PT
    EMU --> W
    W --> N
    PT --> PGU
    PGU --> N
    N --> L
    L --> P
    P --> SW1
    SW1 -- "распознан" --> CR
    SW1 -- "не распознан, попытка 1" --> RW
    RW --> L
    SW1 -- "не распознан, попытка 2" --> ESC
    CR --> FM
    ESC --> FM
    FM --> SW2
    SW2 -- "telegram" --> TS
    SW2 -- "эмулятор" --> R
    R -- "JSON: reply + order_id" --> EMU
    CR --> API
    ESC --> API
    API --> DB
    ADM --> DB
    UI --> ADM
```

## Компоненты

| Компонент | Технологии | Роль |
|-----------|------------|------|
| n8n workflow | n8n, HTTP Request, Code, Switch, Wait, Webhook, Telegram | оркестрация всего флоу; LLM-вызов делает сам n8n |
| LLM | OpenRouter, бесплатные модели (`:free`, по умолчанию `nvidia/nemotron-3-super-120b-a12b:free`) | свободный текст → строгий JSON (услуга, поля, срочность, имя, контакт, valid) |
| Backend | Python, FastAPI, pydantic, SQLAlchemy, SQLite | приём структурированных заказов, дедуп, статусы, подтверждения, админка |
| Эмулятор чата | static HTML/JS (отдаёт backend) | демо без реального Telegram-токена: шлёт webhook в n8n, рисует ответ бота |
| Инфраструктура | docker compose, healthchecks | `docker compose up` поднимает всё |

## Поток данных (успешный путь)

1. Клиент пишет текстом в Telegram **или** в эмуляторе (`POST /webhook/order-bot`, body `{text, name, source}`).
2. Приём из Telegram — polling-цепочка: «TG: расписание опроса» (каждые 30 с) → «TG: смещение (offset)» → «TG: getUpdates» (long poll 25 с, токен из `TELEGRAM_BOT_TOKEN` в окружении n8n) → «TG: новые сообщения» (offset в static data воркфлоу, первый опрос отмечает накопившееся прочитанным). Встроенный «Telegram Trigger» — webhook-режим, для него нужен публичный URL, поэтому нода выключена.
3. «Нормализация ввода» приводит оба формата к `{text, chat_id, name, source}` и подставляет system-промпт.
3. «LLM: Извлечь заказ» — POST в OpenRouter (ключ из переменных окружения контейнера n8n, не из credentials). Температура 0.1.
4. «Разбор ответа LLM» вырезает JSON (терпим markdown-обёртки), проверяет `valid` и `service_type`.
5. Switch: распознан → «Создать заказ»; не распознан → пауза 3 с и повтор; вторая неудача → «Эскалация оператору» (заказ с услугой «Ручная обработка» попадает в админку).
6. Backend: pydantic-валидация → дедуп по sha256 нормализованного текста (повтор → 200 + `duplicate: true`) → статус `new` → генерация `confirmation_text`.
7. «Финальное сообщение» → Switch по источнику: Telegram `sendMessage` или `Respond to Webhook` (JSON `{ok, reply, order_id, escalated}`).
8. В эмуляторе у сообщения появляется кнопка «Подтвердить заказ» → `POST /orders/{id}/confirm` → статус `confirmed` (видно в админке).

## Обработка ошибок

- HTTP-нода LLM: встроенный ретрай (2 попытки, пауза 2 с) + `onError: continue` — при недоступности API заказ уходит в эскалацию, клиент получает честное сообщение.
- Ноды записи в backend: `onError: continue` — если backend недоступен, клиенту отвечается «оператор подключится вручную».
- Пустой текст сообщения — явная ошибка выполнения ноды нормализации (видно в executions n8n).
