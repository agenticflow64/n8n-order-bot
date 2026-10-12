"""Тексты и логика Telegram-ветки бота: приветствие и inline-кнопки.

Копируется в Code-ноды workflow n8n (workflows/order-bot.json):
«Нормализация ввода» (детект /start, /help), «Приветствие», «Кнопка: ответ».
Синхронизируйте вручную при правках.
"""

import re
from typing import Optional

WELCOME_TEXT = (
    "Привет 👋 Я оформляю заказы в один шаг: пишете как удобно, "
    "я раскладываю на детали, даю номер и передаю в работу.\n\n"
    "Например, хватит такого:\n"
    "• надо стрижку собаке на выходные, телефон 89161234567\n"
    "• ноут асус не включается, я Дима, можете вечером?\n"
    "• срочно нужен мастер, кран потёк, адрес Ленина 5\n\n"
    "Пишите заказ прямо сюда, своим языком: с опечатками тоже сработает. "
    "Через несколько секунд пришлю сводку и две кнопки, подтвердить или отменить."
)

# /start, /help, /start@botname, «/start привет» — всё это приветствие
_WELCOME_RE = re.compile(r"^/(start|help)(@[\w_]+)?(\s|$)", re.IGNORECASE)

_CALLBACK_RE = re.compile(r"^(confirm|cancel):(\d+)$")


def is_welcome(text: str) -> bool:
    """/start или /help — не гоняем в LLM, отвечаем приветствием."""
    return bool(_WELCOME_RE.match((text or "").strip()))


def parse_callback_data(data: str) -> Optional[tuple[str, int]]:
    """«confirm:12» → ('confirm', 12); чужой callback_data → None."""
    match = _CALLBACK_RE.match((data or "").strip())
    if match is None:
        return None
    return match.group(1), int(match.group(2))


def callback_reply(action: str, backend_response: Optional[dict]) -> dict:
    """Реакция на нажатие inline-кнопки.

    Возвращает {'alert': str, 'edit': str}: alert уходит в answerCallbackQuery
    (всплывашка), edit — новый текст сообщения с кнопками ('' — не менять).
    """
    if action not in ("confirm", "cancel"):
        return {"alert": "Кнопка не распознана, напишите заказ текстом", "edit": ""}

    status = (backend_response or {}).get("status")
    order_id = (backend_response or {}).get("id")
    if status == "confirmed":
        return {
            "alert": "Принято",
            "edit": f"Заказ №{order_id} подтверждён, ждите звонка.",
        }
    if status == "cancelled":
        return {
            "alert": "Готово",
            "edit": f"Заказ №{order_id} отменён. Напишите новый в любой момент.",
        }
    # 404/409/сбой сети — честная всплывашка, сообщение с кнопками не трогаем
    return {"alert": "Не получилось, попробуйте ещё раз или напишите в чат", "edit": ""}
