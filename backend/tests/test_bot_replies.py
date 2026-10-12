"""Юнит-тесты Telegram-ветки бота: приветствие, кнопки, endpoint отмены.

Логика продублирована в Code-нодах workflow n8n — эти тесты фиксируют
контракт (тексты, формат callback_data), который ноды обязаны соблюдать.
"""

from app.bot_replies import WELCOME_TEXT, callback_reply, is_welcome, parse_callback_data


# --- is_welcome: /start и /help не должны уходить в LLM ---


def test_is_welcome_variants():
    assert is_welcome("/start")
    assert is_welcome("/start ")
    assert is_welcome("/START")
    assert is_welcome("/help")
    assert is_welcome("/start@auto_llm_1_bot")
    assert is_welcome("/start привет")
    assert is_welcome("  /start  ")


def test_is_not_welcome_orders():
    # заказ, начинающийся похоже, — это заказ, а не приветствие
    assert not is_welcome("надо стрижку собаке на выходные, срочно!!")
    assert not is_welcome("/старт")
    assert not is_welcome("start без слэша")
    assert not is_welcome("")
    assert not is_welcome("что почём за стрижку?")


def test_welcome_text_content():
    # без длинных тире и эмодзи-спама; есть примеры и призыв написать
    assert "—" not in WELCOME_TEXT
    assert WELCOME_TEXT.count("👋") == 1
    assert "срочно" in WELCOME_TEXT  # пример формулировки заказа
    assert "пишите" in WELCOME_TEXT.lower()


# --- parse_callback_data: формат кнопок confirm:{id} / cancel:{id} ---


def test_parse_callback_data():
    assert parse_callback_data("confirm:12") == ("confirm", 12)
    assert parse_callback_data("cancel:3") == ("cancel", 3)
    assert parse_callback_data("confirm:abc") is None
    assert parse_callback_data("delete:12") is None
    assert parse_callback_data("") is None


# --- callback_reply: alert для answerCallbackQuery, edit для editMessageText ---


def test_callback_reply_confirm():
    r = callback_reply("confirm", {"status": "confirmed", "id": 7})
    assert r["edit"] == "Заказ №7 подтверждён, ждите звонка."
    assert r["alert"]


def test_callback_reply_cancel():
    r = callback_reply("cancel", {"status": "cancelled", "id": 7})
    assert r["edit"] == "Заказ №7 отменён. Напишите новый в любой момент."
    assert r["alert"]


def test_callback_reply_failures():
    # backend недоступен / 404 / 409 — сообщение с кнопками не меняем
    for bad in (None, {}, {"detail": "Заказ не найден"}, {"status": "done"}):
        r = callback_reply("confirm", bad)
        assert r["edit"] == ""
        assert r["alert"]
    # чужая callback_data
    r = callback_reply("unknown", None)
    assert r["edit"] == ""


# --- endpoint отмены ---


def _create(client):
    return client.post(
        "/orders",
        json={
            "service_type": "стрижка собак",
            "fields": {},
            "urgency": "normal",
            "raw_text": "стрижку собаке на субботу, пудель, 89161234567",
            "source": "telegram",
        },
    ).json()


def test_cancel_endpoint(client):
    oid = _create(client)["id"]
    r = client.post(f"/orders/{oid}/cancel")
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"
    # после отмены подтвердить нельзя (409 от confirm-эндпоинта)
    assert client.post(f"/orders/{oid}/confirm").status_code == 409


def test_cancel_endpoint_guards(client):
    assert client.post("/orders/999999/cancel").status_code == 404
    oid = _create(client)["id"]
    client.patch(f"/orders/{oid}", json={"status": "done"})
    assert client.post(f"/orders/{oid}/cancel").status_code == 409
