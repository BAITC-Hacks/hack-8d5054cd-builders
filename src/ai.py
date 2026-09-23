"""OpenAI calls with bounded latency and a deterministic local demo fallback."""

from __future__ import annotations

import json
import os
from typing import Any

from dotenv import load_dotenv

from .models import CARD_FIELDS

load_dotenv()

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
DEMO_MODE = os.getenv("DEMO_MODE", "false").strip().casefold() in {
    "1", "true", "yes", "on", "да"
}

DEMO_DRAFT = (
    "Наша сеть магазинов хочет сократить число незавершённых онлайн-заказов. "
    "Пока непонятно, на каком шаге покупатели уходят и что нужно проверить."
)

DEMO_ANSWERS: dict[str, str] = {
    "title": "Снижение числа незавершённых онлайн-заказов",
    "context": (
        "Сейчас покупатели добавляют товары в корзину на сайте сети магазинов, "
        "но часть из них не завершает оформление заказа."
    ),
    "need": (
        "Нужно определить основные шаги оформления, на которых покупатели "
        "прерывают заказ, и предложить способ снизить такие уходы."
    ),
    "users": "Решением будут пользоваться команда электронной торговли и аналитики сети.",
    "data": (
        "Бизнес может предоставить обезличенные события сайта по просмотрам, "
        "корзинам и оформленным заказам за последние три месяца."
    ),
    "constraints": (
        "Работа рассчитана на четыре недели; персональные данные покупателей "
        "команде не передаются."
    ),
    "expected_result": (
        "Нужны анализ этапов оформления, список проверяемых причин ухода "
        "и прототип одного приоритетного улучшения."
    ),
    "success_criteria": (
        "Бизнес сможет воспроизвести расчёт для каждого этапа и проверить "
        "прототип на пяти сценариях оформления."
    ),
    "contact": "Контакт со стороны бизнеса — руководитель электронной торговли.",
    "collaboration_format": (
        "Команда встречается с бизнесом онлайн один раз в неделю и получает "
        "обратную связь по промежуточным результатам."
    ),
}

DEMO_QUESTIONS = [
    {"field": "title", "question": "Как кратко назвать эту практическую задачу?"},
    {"field": "context", "question": "Что происходит сейчас и в каком процессе возникает проблема?"},
    {"field": "need", "question": "Что именно нужно изменить или решить?"},
    {"field": "users", "question": "Кто будет пользоваться решением или результатом?"},
    {"field": "data", "question": "Какие данные, материалы или примеры сможет предоставить бизнес?"},
    {"field": "constraints", "question": "Какие есть сроки, ограничения по доступам или технологиям?"},
    {"field": "expected_result", "question": "Какой конкретный результат должна подготовить команда?"},
    {"field": "success_criteria", "question": "По каким признакам бизнес поймёт, что результат подходит?"},
    {"field": "contact", "question": "Кто будет контактным лицом со стороны бизнеса?"},
    {"field": "collaboration_format", "question": "Как команда будет встречаться с бизнесом и получать обратную связь?"},
]


def _fallback_analysis() -> dict[str, Any]:
    return {
        "missing_fields": [key for key in CARD_FIELDS if key != "title"],
        "questions": [dict(item) for item in DEMO_QUESTIONS],
        "mode": "demo",
    }


def _get_client():
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        from openai import OpenAI

        return OpenAI(api_key=api_key, timeout=12.0, max_retries=0)
    except Exception:
        return None


def _parse_json(content: str) -> dict[str, Any]:
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise ValueError("AI ответил не JSON-объектом")
    return parsed


def analyze_draft(draft: str) -> dict[str, Any]:
    """Найти пробелы в черновике и вернуть вопросы с привязкой к полям."""
    if DEMO_MODE:
        return _fallback_analysis()

    client = _get_client()
    if client is None:
        return _fallback_analysis()

    schema = ", ".join(f'"{key}"' for key in CARD_FIELDS)
    try:
        response = client.chat.completions.create(
            model=MODEL,
            temperature=0.2,
            max_tokens=1200,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Ты помогаешь бизнесу подготовить практическую задачу студентам. "
                        "Определи пробелы и задай не менее трёх коротких уточняющих вопросов. "
                        "Не придумывай факты. Верни только JSON-объект с ключами "
                        "missing_fields (массив ключей полей) и questions "
                        "(массив объектов {field, question}). Допустимые ключи полей: "
                        f"{schema}. Вопросы должны уточнять только отсутствующие или неясные сведения."
                    ),
                },
                {"role": "user", "content": f"Черновик бизнеса:\n{draft}"},
            ],
        )
        content = response.choices[0].message.content or "{}"
        raw = _parse_json(content)
        valid_fields = set(CARD_FIELDS)
        questions = []
        for item in raw.get("questions", []):
            if not isinstance(item, dict):
                continue
            field = str(item.get("field", "")).strip()
            question = str(item.get("question", "")).strip()
            if field in valid_fields and question:
                questions.append({"field": field, "question": question[:500]})
        if len(questions) < 3:
            return _fallback_analysis()
        missing = [
            field for field in raw.get("missing_fields", [])
            if isinstance(field, str) and field in valid_fields
        ]
        return {"missing_fields": missing, "questions": questions[:12], "mode": "openai"}
    except Exception:
        # На площадке сетевой сбой не должен прерывать демонстрацию. Не пишем
        # черновик, ключи или текст исключения в логи.
        return _fallback_analysis()


def _fallback_card(draft: str, answers: dict[str, str]) -> dict[str, str]:
    """Собрать карточку только из текста черновика и ответов пользователя."""
    card = {key: "" for key in CARD_FIELDS}
    for key in CARD_FIELDS:
        answer = str(answers.get(key, "") or "").strip()
        if answer:
            card[key] = answer

    source_draft = draft.strip()
    if not card["title"]:
        first_line = next((line.strip() for line in source_draft.splitlines() if line.strip()), "")
        card["title"] = first_line[:90]
    if source_draft and not card["context"]:
        card["context"] = source_draft
    elif source_draft and card["context"] != source_draft:
        card["context"] = f"{source_draft}\n\nУточнение бизнеса: {card['context']}"
    return card


def build_card(draft: str, answers: dict[str, str]) -> dict[str, Any]:
    """Преобразовать черновик и ответы в структуру карточки."""
    if DEMO_MODE:
        return {"card": _fallback_card(draft, answers), "mode": "demo"}

    client = _get_client()
    if client is None:
        return {"card": _fallback_card(draft, answers), "mode": "demo"}

    try:
        response = client.chat.completions.create(
            model=MODEL,
            temperature=0.1,
            max_tokens=1500,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Собери редактируемую карточку бизнес-задачи в JSON. "
                        "Используй только факты из черновика и ответов ниже: "
                        "не делай предположений, не добавляй сроки, метрики, технологии, "
                        "обещания или другие сведения от себя. Если сведений нет, оставь "
                        "строковое поле пустым. Допустимые ключи: "
                        + ", ".join(CARD_FIELDS)
                        + ". Верни JSON-объект, где каждое поле — короткая строка."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {"draft": draft, "answers": answers},
                        ensure_ascii=False,
                    ),
                },
            ],
        )
        raw = _parse_json(response.choices[0].message.content or "{}")
        card = {
            key: str(raw.get(key, "") or "").strip()[:4000]
            for key in CARD_FIELDS
        }
        # Заголовок и контекст не должны теряться, если модель вернула неполный JSON.
        fallback = _fallback_card(draft, answers)
        for key in ("title", "context"):
            if not card[key]:
                card[key] = fallback[key]
        return {"card": card, "mode": "openai"}
    except Exception:
        return {"card": _fallback_card(draft, answers), "mode": "demo"}
