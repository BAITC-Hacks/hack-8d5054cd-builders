"""Структуры данных и общие поля карточек для MVP."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4
from urllib.parse import urlsplit


CARD_FIELDS: dict[str, str] = {
    "title": "Название",
    "context": "Контекст",
    "need": "Потребность",
    "users": "Пользователи",
    "data": "Данные и материалы",
    "constraints": "Ограничения",
    "expected_result": "Ожидаемый результат",
    "success_criteria": "Критерии успеха",
    "contact": "Контакт",
    "collaboration_format": "Формат взаимодействия",
}

SCORED_FIELDS = tuple(key for key in CARD_FIELDS if key != "title")


def make_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def is_valid_prototype_url(value: str) -> bool:
    if not value:
        return True
    if any(char.isspace() for char in value):
        return False
    try:
        parsed = urlsplit(value)
        return (
            parsed.scheme in {"http", "https"} and bool(parsed.hostname)
            and parsed.username is None and parsed.password is None
            and (parsed.port is None or 0 < parsed.port <= 65535)
        )
    except ValueError:
        return False


@dataclass
class TaskCard:
    title: str = ""
    context: str = ""
    need: str = ""
    users: str = ""
    data: str = ""
    constraints: str = ""
    expected_result: str = ""
    success_criteria: str = ""
    contact: str = ""
    collaboration_format: str = ""
    id: str = field(default_factory=lambda: make_id("task"))
    owner_id: str = ""
    status: str = "draft"
    created_at: str = field(default_factory=utc_now)
    rating: int = 0
    topic: str = "Другое"
    confirmed_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "TaskCard":
        known = {key: raw.get(key, "") for key in CARD_FIELDS}
        known.update(
            id=raw.get("id") or make_id("task"),
            owner_id=raw.get("owner_id", ""),
            status=raw.get("status", "draft"),
            created_at=raw.get("created_at") or utc_now(),
            rating=int(raw.get("rating", 0) or 0),
            topic=raw.get("topic") or "Другое",
            confirmed_at=raw.get("confirmed_at", ""),
        )
        return cls(**known)


@dataclass
class Application:
    task_id: str
    team_name: str
    idea: str
    plan: str
    prototype_url: str = ""
    team_id: str = ""
    id: str = field(default_factory=lambda: make_id("application"))
    status: str = "pending"
    created_at: str = field(default_factory=utc_now)
    # At the end to preserve older positional arguments and saved proposals.
    timeline: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TeamProfile:
    name: str
    interests: list[str]
    skills: list[str]
    technologies: list[str]
    id: str = field(default_factory=lambda: make_id("team"))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
