#!/usr/bin/env python3
"""Замер точности извлечения заказа LLM на sample-наборе (реальный API OpenRouter).

Использование:
    set -a; source .env; set +a
    python3 scripts/measure_accuracy.py [--limit N] [--model MODEL]

Печатает markdown-таблицу по каждому сэмплу и итоговые метрики.
Результаты используются в портфолио с пометкой «демо».
"""

import argparse
import json
import os
import re
import statistics
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.prompt import DEFAULT_MODEL, SYSTEM_PROMPT  # noqa: E402

SAMPLES = json.loads((Path(__file__).parent / "samples.json").read_text(encoding="utf-8"))


def digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def got_valid(parsed: dict | None) -> bool:
    return bool(parsed) and parsed.get("valid") is not False and bool(parsed.get("service_type"))


def contact_ok(expected, actual) -> bool:
    if expected is None:
        return not actual
    if not actual:
        return False
    kind = expected["kind"]
    a = str(actual)
    if kind == "digits":
        return digits(a).endswith(expected["value"][-10:])
    if kind == "tg":
        return expected["value"].lower() in a.lower().replace(" ", "")
    if kind == "email":
        return expected["value"].lower() in a.lower()
    return False


def score(sample: dict, parsed: dict | None) -> dict:
    exp = sample["expected"]
    valid = got_valid(parsed)
    r = {
        "valid": valid == exp["valid"],
        "service": True,
        "urgency": True,
        "contact": contact_ok(exp["contact"], (parsed or {}).get("contact")),
        "name": True,
    }
    if exp["valid"]:
        svc = str((parsed or {}).get("service_type") or "").lower()
        r["service"] = any(k in svc for k in exp["service_keywords"])
        r["urgency"] = (parsed or {}).get("urgency") == exp["urgency"]
        if exp["customer_name"]:
            r["name"] = str((parsed or {}).get("customer_name") or "").strip().lower() == exp["customer_name"].lower()
    return r


def call_llm(client: httpx.Client, base_url: str, api_key: str, model: str, text: str) -> tuple[str, float]:
    t0 = time.monotonic()
    r = client.post(
        f"{base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "temperature": 0.1,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
        },
        timeout=90,
    )
    dt = time.monotonic() - t0
    r.raise_for_status()
    content = r.json()["choices"][0]["message"]["content"]
    return content, dt


def parse_content(content: str) -> dict | None:
    m = re.search(r"\{[\s\S]*\}", content or "")
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="обработать только N сэмплов")
    ap.add_argument("--model", default=os.environ.get("OPENROUTER_MODEL") or DEFAULT_MODEL)
    args = ap.parse_args()

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        sys.exit("OPENROUTER_API_KEY не задан (source .env)")
    base_url = os.environ.get("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1"

    samples = SAMPLES[: args.limit] if args.limit else SAMPLES
    total = {k: 0 for k in ("valid", "service", "urgency", "contact", "name", "overall")}
    latencies = []
    rows = []

    with httpx.Client() as client:
        for s in samples:
            try:
                content, dt = call_llm(client, base_url, api_key, args.model, s["text"])
            except Exception as e:  # noqa: BLE001
                rows.append((s["id"], "ОШИБКА API: " + str(e)[:60], None, 0.0))
                for k in total:
                    total[k] += 0
                latencies.append(0.0)
                continue
            parsed = parse_content(content)
            sc = score(s, parsed)
            overall = all(sc.values())
            for k, v in {**sc, "overall": overall}.items():
                total[k] += int(v)
            latencies.append(dt)
            svc = (parsed or {}).get("service_type") or "—"
            urg = (parsed or {}).get("urgency") or "—"
            rows.append((s["id"], f"{svc} / {urg}", overall, dt))

    n = len(samples)
    print(f"# Замер точности извлечения (демо, модель: {args.model}, n={n})\n")
    print("| # | извлечено | всё верно | время, с |")
    print("|---|-----------|-----------|----------|")
    for rid, info, ok, dt in rows:
        print(f"| {rid} | {info} | {'да' if ok else 'нет'} | {dt:.1f} |")
    print()
    for k, v in total.items():
        label = {
            "valid": "валидность определена верно",
            "service": "тип услуги",
            "urgency": "срочность",
            "contact": "контакт",
            "name": "имя клиента",
            "overall": "все поля верно",
        }[k]
        print(f"- {label}: {v}/{n} ({v / n * 100:.0f}%)")
    nz = [x for x in latencies if x > 0]
    if nz:
        print(f"- время ответа LLM: медиана {statistics.median(nz):.1f} с, среднее {statistics.mean(nz):.1f} с, макс {max(nz):.1f} с")


if __name__ == "__main__":
    main()
