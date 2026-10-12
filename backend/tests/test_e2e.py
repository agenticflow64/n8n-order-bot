"""E2E-сквозняк: «клиент пишет в свободной форме» → оркестрация (как в n8n,
LLM замокан) → в БД появился структурированный заказ → подтверждение сгенерировано.

Оркестратор повторяет цепочку нод workflow (workflows/order-bot.json):
Нормализация → LLM-извлечение (мок) → Разбор → POST /orders → Финальное сообщение → confirm.
"""

import pytest

# «Мок LLM»: текст клиента → JSON, который вернула бы бесплатная модель OpenRouter.
LLM_MOCK = {
    "привет, надо стрижку собаке на выходные, зовут Бобик, телефон 89161234567. срочно!!": {
        "service_type": "стрижка собак",
        "fields": {"кличка": "Бобик", "дата": "выходные"},
        "urgency": "urgent",
        "customer_name": None,
        "contact": "+79161234567",
        "valid": True,
    },
    "ноут асус x515 не включается(( мой номер 8-921-333-44-55, Дима": {
        "service_type": "ремонт ноутбуков",
        "fields": {"модель": "асус x515"},
        "urgency": "normal",
        "customer_name": "Дима",
        "contact": "+79213334455",
        "valid": True,
    },
    # мусорный текст → valid=false → ветка эскалации оператору
    "а вы вообще чё за контора??": {
        "service_type": None,
        "fields": {},
        "urgency": "normal",
        "customer_name": None,
        "contact": None,
        "valid": False,
    },
}


def fake_llm_extract(text: str) -> dict:
    return LLM_MOCK.get(text.strip(), {"service_type": None, "fields": {}, "urgency": "normal", "customer_name": None, "contact": None, "valid": False})


def orchestrate(client, text: str, source: str = "emulator") -> dict:
    """Повторяет логику workflow: валид? → создать заказ → финальное сообщение."""
    parsed = fake_llm_extract(text)
    valid = parsed["valid"] and parsed.get("service_type")

    if valid:
        body = {
            "service_type": parsed["service_type"],
            "fields": parsed.get("fields") or {},
            "urgency": parsed.get("urgency") or "normal",
            "customer_name": parsed.get("customer_name") or None,
            "contact": parsed.get("contact") or None,
            "raw_text": text,
            "source": source,
        }
    else:
        body = {
            "service_type": "Ручная обработка",
            "fields": {"проблема": "LLM не смог извлечь заказ", "попыток": 2},
            "urgency": "normal",
            "customer_name": None,
            "contact": None,
            "raw_text": text,
            "source": source,
            "note": "LLM вернул не-JSON или не распознал услугу",
        }

    r = client.post("/orders", json=body)
    assert r.status_code in (200, 201), r.text
    order = r.json()

    reply = order["confirmation_text"]
    escalated = order["service_type"] == "Ручная обработка"
    return {
        "reply": reply,
        "order_id": order["id"],
        "escalated": escalated,
        "order": order,
    }


@pytest.mark.e2e
def test_e2e_structured_order_lands_in_db(client):
    text = "привет, надо стрижку собаке на выходные, зовут Бобик, телефон 89161234567. срочно!!"
    result = orchestrate(client, text)

    order_id = result["order_id"]
    assert order_id is not None

    # в БД появился СТРУКТУРИРОВАННЫЙ заказ
    stored = client.get(f"/orders/{order_id}").json()
    assert stored["service_type"] == "стрижка собак"
    assert stored["urgency"] == "urgent"
    assert stored["fields"]["кличка"] == "Бобик"
    assert stored["contact"] == "+79161234567"
    assert stored["raw_text"] == text
    assert stored["status"] == "new"
    assert stored["source"] == "emulator"

    # подтверждение сгенерировано: человекочитаемая сводка с номером
    assert "✅ Заказ принят!" in result["reply"]
    assert f"#{order_id}" in result["reply"]
    assert "Бобик" in result["reply"]


@pytest.mark.e2e
def test_e2e_client_confirms_order(client):
    text = "ноут асус x515 не включается(( мой номер 8-921-333-44-55, Дима"
    result = orchestrate(client, text)
    order_id = result["order_id"]

    # клиент отвечает «да» → эмуляция подтверждения
    r = client.post(f"/orders/{order_id}/confirm")
    assert r.status_code == 200
    assert r.json()["status"] == "confirmed"
    assert r.json()["confirmed_at"] is not None

    # дедуп: повторное «отправление» того же текста не создаёт новый заказ
    again = orchestrate(client, text)
    assert again["order_id"] == order_id
    assert len(client.get("/orders").json()) == 1


@pytest.mark.e2e
def test_e2e_garbage_escalates_to_operator(client):
    text = "а вы вообще чё за контора??"
    result = orchestrate(client, text)

    assert result["escalated"] is True
    assert "оператор" in result["reply"].lower()
    stored = client.get(f"/orders/{result['order_id']}").json()
    assert stored["service_type"] == "Ручная обработка"
    assert stored["raw_text"] == text
