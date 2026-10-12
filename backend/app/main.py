"""FastAPI: приём структурированных заказов от n8n + админ-API + UI."""

import hashlib
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .confirmations import build_confirmation
from .db import SessionLocal, init_db
from .models import Order, utcnow
from .schemas import OrderCreate, OrderOut, OrderStatus, OrderUpdate

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="n8n-order-bot backend", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def hash_text(text: str) -> str:
    normalized = " ".join(text.lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def order_to_out(order: Order, duplicate: bool = False) -> OrderOut:
    data = {
        "id": order.id,
        "service_type": order.service_type,
        "fields": json.loads(order.fields_json or "{}"),
        "urgency": order.urgency,
        "customer_name": order.customer_name,
        "contact": order.contact,
        "raw_text": order.raw_text,
        "source": order.source,
        "status": order.status,
        "note": order.note,
        "created_at": order.created_at.isoformat() + "Z",
        "updated_at": order.updated_at.isoformat() + "Z",
        "confirmed_at": order.confirmed_at.isoformat() + "Z" if order.confirmed_at else None,
    }
    return OrderOut(**data, confirmation_text=build_confirmation(data), duplicate=duplicate)


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "n8n-order-bot-backend"}


@app.post("/orders")
def create_order(payload: OrderCreate, response: Response, db: Session = Depends(get_db)):
    text_hash = hash_text(payload.raw_text)
    existing = db.query(Order).filter(Order.text_hash == text_hash).first()
    if existing is not None:
        response.status_code = 200
        return order_to_out(existing, duplicate=True)

    order = Order(
        service_type=payload.service_type,
        fields_json=json.dumps(payload.fields, ensure_ascii=False),
        urgency=payload.urgency.value,
        customer_name=payload.customer_name,
        contact=payload.contact,
        raw_text=payload.raw_text,
        text_hash=text_hash,
        source=payload.source.value,
        status="new",
        note=payload.note,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    response.status_code = 201
    return order_to_out(order, duplicate=False)


@app.get("/orders")
def list_orders(
    status: Optional[OrderStatus] = None,
    service_type: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(Order)
    if status is not None:
        query = query.filter(Order.status == status.value)
    if service_type:
        query = query.filter(Order.service_type.ilike(f"%{service_type}%"))
    if source:
        query = query.filter(Order.source == source)
    orders = query.order_by(Order.id.desc()).offset(offset).limit(limit).all()
    return [order_to_out(o) for o in orders]


@app.get("/orders/{order_id}")
def get_order(order_id: int, db: Session = Depends(get_db)):
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    return order_to_out(order)


@app.patch("/orders/{order_id}")
def update_order(order_id: int, payload: OrderUpdate, db: Session = Depends(get_db)):
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    order.status = payload.status.value
    if payload.status == OrderStatus.confirmed and order.confirmed_at is None:
        order.confirmed_at = utcnow()
    db.commit()
    db.refresh(order)
    return order_to_out(order)


@app.post("/orders/{order_id}/confirm")
def confirm_order(order_id: int, db: Session = Depends(get_db)):
    """Эмуляция подтверждения заказа клиентом («да» в чате / кнопка)."""
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    if order.status == "cancelled":
        raise HTTPException(status_code=409, detail="Отменённый заказ нельзя подтвердить")
    order.status = "confirmed"
    if order.confirmed_at is None:
        order.confirmed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    db.refresh(order)
    return order_to_out(order)


@app.post("/orders/{order_id}/cancel")
def cancel_order(order_id: int, db: Session = Depends(get_db)):
    """Отмена заказа кнопкой «✗ Отменить» в Telegram."""
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    if order.status == "done":
        raise HTTPException(status_code=409, detail="Выполненный заказ нельзя отменить")
    order.status = "cancelled"
    db.commit()
    db.refresh(order)
    return order_to_out(order)


@app.get("/api/stats")
def stats(db: Session = Depends(get_db)):
    counts = {s.value: 0 for s in OrderStatus}
    for row in db.query(Order.status, Order.id).all():
        counts[row[0]] = counts.get(row[0], 0) + 1
    return {"total": sum(counts.values()), "by_status": counts}


@app.get("/", include_in_schema=False)
def admin_page():
    return FileResponse(STATIC_DIR / "admin.html", media_type="text/html")


@app.get("/chat", include_in_schema=False)
def chat_page():
    return FileResponse(STATIC_DIR / "chat.html", media_type="text/html")
