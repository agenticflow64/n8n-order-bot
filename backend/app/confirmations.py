"""Генерация человекочитаемых подтверждений для клиента."""

MANUAL_SERVICE = "Ручная обработка"

URGENCY_RU = {
    "low": "не срочно",
    "normal": "обычная",
    "high": "высокая",
    "urgent": "срочная (🔥)",
}

STATUS_RU = {
    "new": "новый",
    "confirmed": "подтверждён",
    "in_progress": "в работе",
    "done": "выполнен",
    "cancelled": "отменён",
}


def build_confirmation(order: dict) -> str:
    """Сводка, которую бот отправляет клиенту после приёма заказа."""
    oid = order.get("id")
    service = order.get("service_type") or ""

    if service == MANUAL_SERVICE:
        lines = [
            "⚠️ Не удалось автоматически оформить заказ.",
            f"Оператор уже видит его в панели (#{oid}) и подключится вручную.",
            "Ничего повторять не нужно — мы сами напишем в этот чат.",
        ]
        return "\n".join(lines)

    lines = [
        "✅ Заказ принят!",
        f"🧾 Номер заказа: #{oid}",
        f"🛠 Услуга: {service}",
    ]
    fields = order.get("fields") or {}
    for key, value in fields.items():
        lines.append(f"   • {key}: {value}")
    urgency = order.get("urgency") or "normal"
    lines.append(f"⏱ Срочность: {URGENCY_RU.get(urgency, urgency)}")
    if order.get("customer_name"):
        lines.append(f"👤 Имя: {order['customer_name']}")
    if order.get("contact"):
        lines.append(f"📞 Контакт: {order['contact']}")
    lines.append("")
    lines.append("Если всё верно — подтвердите, ответив «да» или нажав кнопку в чате.")
    return "\n".join(lines)
