"""Прозрачный рейтинг полноты карточки без вызовов AI и внешних сервисов."""

from __future__ import annotations

from typing import Any

from .models import CARD_FIELDS


# Контекст и потребность вместе дают 20 баллов; контакт и формат — ещё 10.
FIELD_WEIGHTS: dict[str, int] = {
    "context": 10,
    "need": 10,
    "data": 20,
    "expected_result": 15,
    "success_criteria": 15,
    "constraints": 10,
    "users": 10,
    "contact": 5,
    "collaboration_format": 5,
}

# Короткий ответ даёт половину веса. Это делает подсказки полезными и для
# частично заполненных карточек, сохраняя формулу детерминированной.
MIN_DETAIL_LENGTH: dict[str, int] = {
    "context": 35,
    "need": 20,
    "data": 15,
    "expected_result": 20,
    "success_criteria": 20,
    "constraints": 14,
    "users": 10,
    "contact": 5,
    "collaboration_format": 12,
}

GROUPS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("Контекст и потребность", "context_need", ("context", "need")),
    ("Данные и материалы", "data", ("data",)),
    ("Ожидаемый результат", "expected_result", ("expected_result",)),
    ("Критерии успеха", "success_criteria", ("success_criteria",)),
    ("Ограничения", "constraints", ("constraints",)),
    ("Пользователи", "users", ("users",)),
    ("Связь с бизнесом", "business_link", ("contact", "collaboration_format")),
)

IMPROVEMENT_HINTS: dict[str, str] = {
    "context": "Опишите, что происходит сейчас и в каком процессе возникает задача.",
    "need": "Сформулируйте, что именно нужно изменить или решить.",
    "data": "Перечислите доступные данные, примеры, документы или источники.",
    "expected_result": "Назовите конкретный результат, который должна подготовить команда.",
    "success_criteria": "Добавьте измеримый признак, по которому бизнес примет результат.",
    "constraints": "Укажите сроки, доступы, технологии или другие границы работы.",
    "users": "Уточните, кто будет пользоваться решением или результатом.",
    "contact": "Укажите человека или канал связи со стороны бизнеса.",
    "collaboration_format": "Опишите, как часто и в каком формате команда сможет получать обратную связь.",
}

PLACEHOLDERS = {
    "-",
    "—",
    "н/д",
    "не указано",
    "неизвестно",
    "пока неизвестно",
    "уточняется",
    "нет данных",
}


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _earned_points(field: str, value: Any) -> int:
    text = _clean_text(value)
    if not text or text.casefold() in PLACEHOLDERS:
        return 0
    weight = FIELD_WEIGHTS[field]
    if len(text) < MIN_DETAIL_LENGTH[field]:
        return weight // 2
    return weight


def calculate_rating(card: dict[str, Any]) -> dict[str, Any]:
    """Вернуть балл, уровень, расшифровку и улучшения для карточки.

    Функция чистая: результат зависит только от переданных полей, не меняет
    карточку и не обращается к Streamlit, файлам, AI или сети.
    """
    per_field = {
        field: _earned_points(field, card.get(field, ""))
        for field in FIELD_WEIGHTS
    }
    score = sum(per_field.values())
    if score <= 39:
        level = "Черновик"
    elif score <= 69:
        level = "Рабочая"
    elif score <= 89:
        level = "Готовая"
    else:
        level = "Приоритетная"

    breakdown = []
    for label, key, fields in GROUPS:
        earned = sum(per_field[field] for field in fields)
        possible = sum(FIELD_WEIGHTS[field] for field in fields)
        breakdown.append({"key": key, "label": label, "earned": earned, "possible": possible})

    improvements = []
    for field, weight in FIELD_WEIGHTS.items():
        earned = per_field[field]
        if earned == weight:
            continue
        improvements.append(
            {
                "field": field,
                "label": CARD_FIELDS[field],
                "potential_points": weight - earned,
                "hint": IMPROVEMENT_HINTS[field],
            }
        )
    improvements.sort(key=lambda item: (-item["potential_points"], item["label"]))

    return {
        "score": score,
        "level": level,
        "breakdown": breakdown,
        "improvements": improvements,
    }
