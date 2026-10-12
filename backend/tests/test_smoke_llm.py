"""Смоук с реальным OpenRouter API (маркеры smoke/slow, по умолчанию выключены).

Запуск: pytest -m smoke --run-smoke
"""

import json
import os
import re

import httpx
import pytest

from app.prompt import DEFAULT_MODEL, SYSTEM_PROMPT

pytestmark = [pytest.mark.smoke, pytest.mark.slow]

SAMPLE = "привет, надо стрижку собаке на выходные, зовут Бобик, телефон 89161234567. срочно!!"


def test_real_llm_returns_valid_json():
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        pytest.skip("OPENROUTER_API_KEY не задан")
    base_url = os.environ.get("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1"
    model = os.environ.get("OPENROUTER_MODEL") or DEFAULT_MODEL

    with httpx.Client(timeout=90) as client:
        r = client.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "temperature": 0.1,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": SAMPLE},
                ],
            },
        )
    assert r.status_code == 200, r.text[:300]
    content = r.json()["choices"][0]["message"]["content"]

    match = re.search(r"\{[\s\S]*\}", content)
    assert match, f"в ответе нет JSON: {content[:200]}"
    parsed = json.loads(match.group(0))

    assert parsed["valid"] is not False
    assert "стрижк" in parsed["service_type"].lower()
    assert parsed["urgency"] == "urgent"
    assert "9161234567" in re.sub(r"\D", "", parsed.get("contact") or "")
