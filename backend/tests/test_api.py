"""API-тесты backend: валидация, дедуп, статусы, админ-API, подтверждения."""


def _payload(**overrides):
    base = {
        "service_type": "стрижка собак",
        "fields": {"кличка": "Бобик", "дата": "выходные"},
        "urgency": "urgent",
        "customer_name": None,
        "contact": "+79161234567",
        "raw_text": "привет, надо стрижку собаке на выходные, зовут Бобик, телефон 89161234567. срочно!!",
        "source": "emulator",
    }
    base.update(overrides)
    return base


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_create_order_valid(client):
    r = client.post("/orders", json=_payload())
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "new"
    assert body["duplicate"] is False
    assert body["service_type"] == "стрижка собак"
    assert body["urgency"] == "urgent"
    assert body["fields"]["кличка"] == "Бобик"
    # подтверждение — человекочитаемая сводка
    conf = body["confirmation_text"]
    assert "стрижка собак" in conf
    assert f"#{body['id']}" in conf
    assert "срочн" in conf.lower()
    assert "+79161234567" in conf


def test_create_order_validation_errors(client):
    # нет услуги
    r = client.post("/orders", json=_payload(service_type=""))
    assert r.status_code == 422
    # слишком короткий текст
    r = client.post("/orders", json=_payload(raw_text="ок"))
    assert r.status_code == 422
    # несуществующая срочность
    r = client.post("/orders", json=_payload(urgency="asap"))
    assert r.status_code == 422
    # несуществующий источник
    r = client.post("/orders", json=_payload(source="whatsapp"))
    assert r.status_code == 422


def test_dedup_by_text_hash(client):
    r1 = client.post("/orders", json=_payload())
    assert r1.status_code == 201
    # тот же текст с другими регистром/пробелами — дубликат
    dup = _payload(raw_text="  ПРИВЕТ, надо стрижку  собаке на выходные, зовут Бобик, телефон 89161234567. срочно!! ")
    r2 = client.post("/orders", json=dup)
    assert r2.status_code == 200
    assert r2.json()["duplicate"] is True
    assert r2.json()["id"] == r1.json()["id"]
    # в списке — один заказ
    orders = client.get("/orders").json()
    assert len(orders) == 1


def test_get_order_and_404(client):
    created = client.post("/orders", json=_payload()).json()
    assert client.get(f"/orders/{created['id']}").status_code == 200
    assert client.get("/orders/999999").status_code == 404


def test_list_filters(client):
    a = client.post("/orders", json=_payload()).json()
    b = client.post(
        "/orders",
        json=_payload(
            service_type="ремонт ноутбуков",
            raw_text="ноут асус x515 не включается вообще(( можно на этой неделе? зовут Дима",
            urgency="normal",
            contact="89213334455",
            customer_name="Дима",
            fields={"модель": "асус x515"},
        ),
    ).json()
    client.patch(f"/orders/{b['id']}", json={"status": "confirmed"})

    assert [o["id"] for o in client.get("/orders", params={"status": "new"}).json()] == [a["id"]]
    assert [o["id"] for o in client.get("/orders", params={"status": "confirmed"}).json()] == [b["id"]]
    svc = client.get("/orders", params={"service_type": "ноут"}).json()
    assert [o["id"] for o in svc] == [b["id"]]
    assert len(client.get("/orders").json()) == 2


def test_patch_statuses(client):
    created = client.post("/orders", json=_payload()).json()
    oid = created["id"]
    for status in ("confirmed", "in_progress", "done"):
        r = client.patch(f"/orders/{oid}", json={"status": status})
        assert r.status_code == 200
        assert r.json()["status"] == status
    # невалидный статус
    assert client.patch(f"/orders/{oid}", json={"status": "closed"}).status_code == 422
    # несуществующий заказ
    assert client.patch("/orders/999999", json={"status": "done"}).status_code == 404
    # PATCH на confirmed заполняет confirmed_at (аналогично confirm-эндпоинту)
    assert client.get(f"/orders/{oid}").json()["confirmed_at"] is not None
    r = client.post(f"/orders/{oid}/confirm")
    assert r.status_code == 200
    assert r.json()["status"] == "confirmed"


def test_confirm_endpoint(client):
    created = client.post("/orders", json=_payload()).json()
    r = client.post(f"/orders/{created['id']}/confirm")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "confirmed"
    assert body["confirmed_at"] is not None
    assert "Заказ принят" in body["confirmation_text"]
    # отменённый подтвердить нельзя
    client.patch(f"/orders/{created['id']}", json={"status": "cancelled"})
    assert client.post(f"/orders/{created['id']}/confirm").status_code == 409


def test_manual_escalation_confirmation(client):
    r = client.post(
        "/orders",
        json=_payload(
            service_type="Ручная обработка",
            raw_text="а вы вообще чё за контора??",
            urgency="normal",
            contact=None,
            fields={},
            note="LLM вернул не-JSON",
        ),
    )
    assert r.status_code == 201
    conf = r.json()["confirmation_text"]
    assert "оператор" in conf.lower()
    assert "Не удалось" in conf


def test_stats(client):
    client.post("/orders", json=_payload())
    b = client.post("/orders", json=_payload(service_type="ремонт ноутбуков", raw_text="ноут не включается, позвоните 89991112233 когда сможете")).json()
    client.patch(f"/orders/{b['id']}", json={"status": "cancelled"})
    s = client.get("/api/stats").json()
    assert s["total"] == 2
    assert s["by_status"]["new"] == 1
    assert s["by_status"]["cancelled"] == 1


def test_admin_and_chat_pages(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Order Bot" in r.text
    assert "#0f172a" in r.text or "0f172a" in r.text
    r = client.get("/chat")
    assert r.status_code == 200
    assert "эмулятор" in r.text.lower() or "Order Bot" in r.text
