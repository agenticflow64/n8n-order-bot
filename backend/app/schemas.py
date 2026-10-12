"""Pydantic-схемы API."""

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class Urgency(str, Enum):
    low = "low"
    normal = "normal"
    high = "high"
    urgent = "urgent"


class OrderStatus(str, Enum):
    new = "new"
    confirmed = "confirmed"
    in_progress = "in_progress"
    done = "done"
    cancelled = "cancelled"


class OrderSource(str, Enum):
    telegram = "telegram"
    emulator = "emulator"
    admin = "admin"


def _clean(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class OrderCreate(BaseModel):
    service_type: str = Field(min_length=2, max_length=200)
    fields: dict[str, Any] = Field(default_factory=dict)
    urgency: Urgency = Urgency.normal
    customer_name: Optional[str] = None
    contact: Optional[str] = None
    raw_text: str = Field(min_length=3, max_length=4000)
    source: OrderSource = OrderSource.emulator
    note: Optional[str] = None

    @field_validator("service_type")
    @classmethod
    def clean_service(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("service_type слишком короткий")
        return v

    @field_validator("customer_name", "contact", "note")
    @classmethod
    def clean_optional(cls, v: Optional[str]) -> Optional[str]:
        return _clean(v)


class OrderUpdate(BaseModel):
    status: OrderStatus


class OrderOut(BaseModel):
    id: int
    service_type: str
    fields: dict[str, Any]
    urgency: str
    customer_name: Optional[str]
    contact: Optional[str]
    raw_text: str
    source: str
    status: str
    note: Optional[str]
    created_at: str
    updated_at: str
    confirmed_at: Optional[str]
    confirmation_text: str
    duplicate: bool = False
