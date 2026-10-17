"""Генерация человекочитаемых подтверждений для клиента."""

MANUAL_SERVICE = "Ручная обработка"

URGENCY_RU = {
    "low": "не срочно",
    "normal": "обычная",
    "high": "высокая",
    "urgent": "срочная",
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
            "Не смог разобрать сообщение, извините.",
            f"Оператор уже видит его (№{oid}) и напишет сюда сам.",
            "Хотите быстрее? Пришлите заказ заново, простыми словами: "
            "какая услуга, когда и телефон.",
        ]
        return "\n".join(lines)

    lines = [
        f"Заказ принят, №{oid}.",
        f"Услуга: {service}",
    ]
    fields = order.get("fields") or {}
    for key, value in fields.items():
        if value is None or value == "None":
            continue
        # контакт уже выведен отдельной строкой (нормализован из сырого текста)
        if str(key).strip().lower() in {"contact", "phone", "телефон", "phone_number"}:
            continue
        lines.append(f"  {key}: {value}")
    urgency = order.get("urgency") or "normal"
    lines.append(f"Срочность: {URGENCY_RU.get(urgency, urgency)}")
    if order.get("customer_name"):
        lines.append(f"Имя: {order['customer_name']}")
    if order.get("contact"):
        lines.append(f"Контакт: {order['contact']}")
    lines.append("")
    lines.append("Всё верно? Нажмите кнопку под этим сообщением.")
    return "\n".join(lines)
