"""Общий каталог: прозрачный порядок и необязательные фильтры.

Фильтры задаёт сама команда. Уровень полноты и тема не ограничивают право
откликнуться; здесь нет назначения исполнителей или персональных признаков.
"""

from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from .rating import calculate_rating


ALL_TOPICS = "Все темы"
ALL_READINESS = "Все уровни"
TOPICS = (
    "Аналитика и данные",
    "Автоматизация процессов",
    "Продукты и сервисы",
    "Маркетинг и продажи",
    "Образование",
    "Другое",
)
READINESS_LEVELS = ("Черновик", "Рабочая", "Готовая", "Приоритетная")


def normalize_topic(value: Any) -> str:
    """Сохранить выбранную человеком тему; старые карточки — «Другое»."""
    return value if isinstance(value, str) and value in TOPICS else "Другое"


def _created_order(value: Any) -> float:
    """Раньше опубликованные карточки идут первыми при равном рейтинге."""
    if not isinstance(value, str):
        return float("inf")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except (ValueError, OverflowError, OSError):
        return float("inf")


def published_catalog(
    tasks: Iterable[dict[str, Any]],
    topic: str = ALL_TOPICS,
    readiness: str = ALL_READINESS,
) -> list[dict[str, Any]]:
    """Вернуть независимые копии опубликованных карточек в порядке каталога.

    Баллы пересчитываются по полям, сохранённый ``rating`` не влияет на место.
    При равном балле раньше созданная карточка идёт первой, затем сравнивается
    ``id`` по алфавиту. Пустая/некорректная дата идёт после корректных дат.
    Без фильтров видны все опубликованные карточки, включая рейтинг 0.
    Фильтры применяются совместно и не меняют глобальное место карточки.

    В копии добавляются ``readiness_level`` и нормализованная ``topic``;
    ``rating`` содержит актуальное число. Исходные карточки не изменяются.
    """
    result = []
    for task in tasks:
        if task.get("status") != "published":
            continue
        actual_topic = normalize_topic(task.get("topic"))
        quality = calculate_rating(task)
        if topic != ALL_TOPICS and actual_topic != topic:
            continue
        if readiness != ALL_READINESS and quality["level"] != readiness:
            continue
        card = deepcopy(task)
        card.update(
            rating=quality["score"],
            readiness_level=quality["level"],
            topic=actual_topic,
        )
        result.append(card)
    result.sort(
        key=lambda card: (
            -card["rating"],
            _created_order(card.get("created_at")),
            str(card.get("id", "")),
        )
    )
    return result


def catalog_position(tasks: Iterable[dict[str, Any]], task_id: str) -> tuple[int | None, int]:
    """Вернуть глобальные (место с 1, всего); отсутствующее место — ``None``.

    Фильтры команды не принимаются намеренно: подпись «место в общем каталоге»
    должна относиться ко всем опубликованным задачам.
    """
    cards = published_catalog(tasks)
    position = next((i for i, card in enumerate(cards, 1) if card.get("id") == task_id), None)
    return position, len(cards)


def next_readiness_target(score: int) -> dict[str, int | str] | None:
    """Следующая цель полноты; 100 баллов не создают дополнительный уровень."""
    if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 100:
        raise ValueError("Рейтинг должен быть целым числом от 0 до 100.")
    for target_score, label in (
        (40, "Рабочая"),
        (70, "Готовая"),
        (90, "Приоритетная"),
        (100, "Все поля заполнены"),
    ):
        if score < target_score:
            return {"target_score": target_score, "points_needed": target_score - score, "label": label}
    return None
