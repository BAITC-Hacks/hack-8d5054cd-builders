"""Milestones with human approval and XP earned only for accepted work.

All public mutations return a deep copy of the submissions list. The caller must
assign that list back to session state. Inputs are never modified. IDs and UTC
timestamps are generated on submission/review; no API or persistent store is used.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from src.models import is_valid_prototype_url, make_id, utc_now


MILESTONES = (
    {
        "id": "plan",
        "title": "План согласован",
        "xp": 20,
        "description": "Опишите согласованный план, границы работы и признаки приёмки.",
    },
    {
        "id": "prototype",
        "title": "Прототип проверен",
        "xp": 40,
        "description": "Покажите прототип и результаты проверки ключевого сценария.",
    },
    {
        "id": "result",
        "title": "Результат принят",
        "xp": 60,
        "description": "Покажите итог и объясните, какие критерии успеха выполнены.",
    },
)

LEVELS = (
    (0, "Старт"),
    (20, "Исследователь"),
    (60, "Создатель"),
    (120, "Практик"),
    (300, "Опытный практик"),
)


def _milestone(stage_id: str) -> dict[str, Any]:
    for stage in MILESTONES:
        if stage["id"] == stage_id:
            return stage
    raise ValueError("Неизвестный этап работы.")


def _published_task(tasks: list[dict], task_id: str) -> dict:
    matches = [task for task in tasks if task.get("id") == task_id]
    if len(matches) != 1 or matches[0].get("status") != "published":
        raise ValueError("Опубликованная задача не найдена.")
    return matches[0]


def _selected(applications: list[dict], task_id: str, team_id: str) -> None:
    if not isinstance(team_id, str) or not team_id.strip() or not any(
        app.get("task_id") == task_id
        and app.get("team_id") == team_id
        and app.get("status") == "selected"
        for app in applications
    ):
        raise ValueError("Сдать этап может только команда, которую выбрал бизнес.")


def _stage_submission(submissions: list[dict], task_id: str, team_id: str, stage_id: str) -> dict | None:
    matches = [
        row for row in submissions
        if row.get("task_id") == task_id
        and row.get("team_id") == team_id
        and row.get("stage_id") == stage_id
    ]
    if len(matches) > 1:
        raise ValueError("Обнаружен повтор этапа. Обновите состояние проекта.")
    return matches[0] if matches else None


def _previous_approved(submissions: list[dict], task_id: str, team_id: str, stage_id: str) -> None:
    for stage in MILESTONES:
        if stage["id"] == stage_id:
            return
        row = _stage_submission(submissions, task_id, team_id, stage["id"])
        if row is None or row.get("status") != "approved":
            raise ValueError("Сначала дождитесь подтверждения предыдущего этапа бизнесом.")


def _text(value: str, label: str, minimum: int, maximum: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label}: требуется текст.")
    value = value.strip()
    if len(value) < minimum or len(value) > maximum:
        raise ValueError(f"{label}: от {minimum} до {maximum} символов.")
    return value


def submit_stage(
    tasks: list[dict],
    applications: list[dict],
    submissions: list[dict],
    task_id: str,
    team_id: str,
    stage_id: str,
    evidence: str,
    url: str = "",
) -> list[dict]:
    """Submit the next stage, or resubmit a stage returned for revision.

    Each (task, team, stage) has one row even when that team sent several
    applications. Prior reviewed attempts are kept in ``history`` on resubmission.
    Selection and submission do not award XP.
    """
    _published_task(tasks, task_id)
    _selected(applications, task_id, team_id)
    _milestone(stage_id)
    _previous_approved(submissions, task_id, team_id, stage_id)
    evidence = _text(evidence, "Описание результата", 20, 4000)
    url = _text(url, "Ссылка", 0, 2048)
    if not is_valid_prototype_url(url):
        raise ValueError("Ссылка должна начинаться с http:// или https:// и содержать адрес сайта.")
    existing = _stage_submission(submissions, task_id, team_id, stage_id)
    if existing and existing.get("status") != "revision":
        raise ValueError("Этот этап уже отправлен или подтверждён. Повторная сдача недоступна.")

    result = deepcopy(submissions)
    if existing:
        row = next(item for item in result if item["id"] == existing["id"])
        previous = {key: deepcopy(value) for key, value in row.items() if key != "history"}
        row.setdefault("history", []).append(previous)
        row["attempt"] += 1
    else:
        row = {
            "id": make_id("stage"),
            "task_id": task_id,
            "team_id": team_id,
            "stage_id": stage_id,
            "attempt": 1,
            "history": [],
        }
        result.append(row)
    row.update(
        evidence=evidence,
        url=url,
        status="pending",
        submitted_at=utc_now(),
        reviewed_at="",
        reviewed_by="",
        feedback="",
        awarded_xp=0,
    )
    return result


def review_stage(
    tasks: list[dict],
    applications: list[dict],
    submissions: list[dict],
    owner_id: str,
    submission_id: str,
    decision: str,
    feedback: str = "",
) -> list[dict]:
    """The owning business accepts work or returns it with actionable feedback."""
    matches = [row for row in submissions if row.get("id") == submission_id]
    if len(matches) != 1:
        raise ValueError("Отправленный этап не найден.")
    existing = matches[0]
    task = _published_task(tasks, existing["task_id"])
    if not isinstance(owner_id, str) or not owner_id.strip() or task.get("owner_id") != owner_id:
        raise ValueError("Подтвердить этап может только владелец задачи.")
    _selected(applications, existing["task_id"], existing["team_id"])
    stage = _milestone(existing["stage_id"])
    _stage_submission(submissions, existing["task_id"], existing["team_id"], existing["stage_id"])
    _previous_approved(submissions, existing["task_id"], existing["team_id"], existing["stage_id"])
    if existing.get("status") != "pending":
        raise ValueError("Рассмотреть можно только этап, ожидающий решения.")
    if decision not in {"approve", "revise"}:
        raise ValueError("Выберите подтверждение или возврат на доработку.")
    feedback = _text(feedback, "Обратная связь", 5 if decision == "revise" else 0, 2000)

    result = deepcopy(submissions)
    row = next(item for item in result if item["id"] == submission_id)
    row.update(
        status="approved" if decision == "approve" else "revision",
        reviewed_at=utc_now(),
        reviewed_by=owner_id,
        feedback=feedback,
        awarded_xp=stage["xp"] if decision == "approve" else 0,
    )
    return result


def project_stages(submissions: list[dict], task_id: str, team_id: str) -> list[dict]:
    """Describe ordered stages for a UI; selection is checked by submit_stage."""
    result = []
    previous_approved = True
    for stage in MILESTONES:
        row = _stage_submission(submissions, task_id, team_id, stage["id"])
        status = row.get("status") if row else ("available" if previous_approved else "locked")
        result.append({**stage, "status": status, "submission": deepcopy(row)})
        previous_approved = previous_approved and status == "approved"
    return result


def team_summary(submissions: list[dict], team_id: str) -> dict[str, Any]:
    """Count each accepted stage once, using fixed XP values rather than stored totals."""
    approved = {
        (row.get("task_id"), row.get("stage_id"))
        for row in submissions
        if row.get("team_id") == team_id and row.get("status") == "approved"
        and row.get("task_id") and row.get("stage_id") in {stage["id"] for stage in MILESTONES}
    }
    stage_ids = {stage_id for _, stage_id in approved}
    xp = sum(_milestone(stage_id)["xp"] for _, stage_id in approved)
    completed_projects = sum(
        all((task_id, stage["id"]) in approved for stage in MILESTONES)
        for task_id in {task_id for task_id, _ in approved}
    )
    level_index = max(index for index, (threshold, _) in enumerate(LEVELS) if xp >= threshold)
    badges = []
    if "plan" in stage_ids:
        badges.append("Первый согласованный план")
    if "prototype" in stage_ids:
        badges.append("Первый проверенный прототип")
    if completed_projects:
        badges.append("Первый принятый результат")
    if completed_projects >= 3:
        badges.append("Три завершённых проекта")
    return {
        "xp": xp,
        "level": level_index + 1,
        "level_name": LEVELS[level_index][1],
        "level_start_xp": LEVELS[level_index][0],
        "next_level_xp": LEVELS[level_index + 1][0] if level_index + 1 < len(LEVELS) else None,
        "badges": badges,
        "approved_stages": len(approved),
        "completed_projects": completed_projects,
    }
