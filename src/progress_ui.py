"""Streamlit views for work confirmed by business and the team's earned XP."""

from __future__ import annotations

from typing import Any

import streamlit as st

from src.models import is_valid_prototype_url
from src.progress import MILESTONES, project_stages, review_stage, submit_stage, team_summary
from src.ui import format_date, page_header, status_badge


PROJECT_XP = sum(stage["xp"] for stage in MILESTONES)
STAGE_LABELS = {
    "available": "Ваш следующий шаг",
    "locked": "Позже",
    "pending": "На проверке",
    "revision": "Нужна доработка",
    "approved": "Принято",
}
STAGE_TITLES = {"plan": "План", "prototype": "Прототип", "result": "Результат"}
STATUS_TONES = {
    "available": "info", "locked": "neutral", "pending": "info",
    "revision": "warning", "approved": "success", "selected": "success",
    "rejected": "neutral",
}
APPLICATION_LABELS = {
    "pending": "На рассмотрении",
    "selected": "Команда выбрана",
    "rejected": "Отклонён",
}


def _submissions() -> list[dict[str, Any]]:
    return st.session_state.get("submissions", [])


def _notice(key: str) -> None:
    message = st.session_state.pop(key, None)
    if message:
        st.success(message)


def _open_team_page(page: str) -> None:
    st.session_state.team_page = page
    st.session_state.saved_team_page = page


def _safe_link(url: str, label: str = "Открыть результат") -> None:
    if url and is_valid_prototype_url(url):
        st.link_button(label, url)


def _roadmap(stages: list[dict[str, Any]]) -> int:
    earned = sum(stage["xp"] for stage in stages if stage["status"] == "approved")
    approved = sum(stage["status"] == "approved" for stage in stages)
    st.progress(approved / len(stages), text=f"Принято {approved} из {len(stages)} этапов · {earned} XP")
    for index, (column, stage) in enumerate(zip(st.columns(len(stages)), stages), start=1):
        with column:
            st.markdown(f"**{index}. {STAGE_TITLES[stage['id']]}**")
            status_badge(STAGE_LABELS[stage["status"]], STATUS_TONES[stage["status"]])
            st.caption(f"{stage['xp']} XP за принятый этап")
    return earned


def _show_evidence(row: dict[str, Any]) -> None:
    st.markdown("**Что сделано и как проверено**")
    st.write(row.get("evidence", ""))
    _safe_link(row.get("url", ""))
    st.caption(f"Версия {row.get('attempt', 1)} · {format_date(row.get('submitted_at', ''))}")


def _history(stages: list[dict[str, Any]]) -> None:
    recorded = [stage for stage in stages if stage.get("submission")]
    if not recorded:
        return
    with st.expander("История этапов и решений"):
        for stage in recorded:
            current = stage["submission"]
            for row in [*current.get("history", []), current]:
                st.markdown(f"**{STAGE_TITLES[stage['id']]} · версия {row.get('attempt', 1)}**")
                status_badge(STAGE_LABELS.get(row.get("status", ""), "Отправлено"), STATUS_TONES.get(row.get("status", ""), "neutral"))
                _show_evidence(row)
                if row.get("reviewed_at"):
                    st.caption(f"Решение: {format_date(row['reviewed_at'])} · {row.get('reviewed_by', '')}")
                if row.get("feedback"):
                    st.markdown("**Обратная связь бизнеса**")
                    st.write(row["feedback"])
                if row.get("status") == "approved":
                    st.caption(f"Начислено {stage['xp']} XP один раз за этот этап.")
                st.divider()


def _criteria(task: dict[str, Any], *, expanded: bool = False) -> None:
    criteria = str(task.get("success_criteria", "") or "").strip()
    with st.expander("Как бизнес оценит результат", expanded=expanded):
        if criteria:
            st.write(criteria)
        else:
            st.info("В карточке ещё нет критериев успеха. Согласуйте их с бизнесом и опишите в первом этапе.")


def render_team_dashboard(team: dict[str, Any], *, compact: bool = False) -> None:
    summary = team_summary(_submissions(), team["id"])
    if compact:
        status_badge(f"{summary['xp']} баллов опыта · {summary['level_name']}", "neutral")
        return
    st.subheader("Опыт команды")
    points, level, projects = st.columns(3)
    points.metric("Подтверждённые XP", summary["xp"])
    level.metric("Уровень команды", summary["level_name"])
    projects.metric("Завершено проектов", summary["completed_projects"])
    next_level = summary["next_level_xp"]
    if next_level is not None:
        start = summary["level_start_xp"]
        st.progress(
            (summary["xp"] - start) / (next_level - start),
            text=f"До следующего уровня: {next_level - summary['xp']} XP",
        )
    st.caption("Баллы опыта (XP) команда получает после принятия этапа бизнесом.")
    with st.expander("Достижения и правила начисления"):
        if summary["badges"]:
            for badge in summary["badges"]:
                st.write(f"✓ {badge}")
        else:
            st.write("Первое достижение откроется, когда бизнес примет план.")
        st.caption(f"План: 20 XP · Прототип: 40 XP · Результат: 60 XP. Всего {PROJECT_XP} XP за проект.")
        st.caption("Каждый этап приносит баллы один раз. Отклик и выбор команды не увеличивают опыт. Рейтинг задачи показывает полноту её описания.")


def render_team_projects(team: dict[str, Any]) -> None:
    page_header("РАБОТА С БИЗНЕСОМ", "Мои проекты", "Выполняйте этапы по порядку и отправляйте результаты на проверку.")
    with st.expander("Опыт и достижения команды"):
        render_team_dashboard(team)
    _notice(f"progress_notice_team_{team['id']}")
    selected_ids = {
        app["task_id"] for app in st.session_state.applications
        if app.get("team_id") == team["id"] and app.get("status") == "selected"
    }
    tasks = [task for task in st.session_state.tasks if task.get("id") in selected_ids and task.get("status") == "published"]
    if not tasks:
        st.info("Здесь появятся задачи, для которых бизнес выбрал вашу команду. Начните с предложения в каталоге.")
        st.button("Перейти в каталог", key=f"projects_browse_{team['id']}", on_click=_open_team_page, args=("Каталог",), type="primary")
        return
    for task in tasks:
        with st.container(border=True):
            st.subheader(task.get("title") or "Задача без названия")
            st.caption(f"Бизнес: {task.get('owner_id', '')}")
            stages = project_stages(_submissions(), task["id"], team["id"])
            _roadmap(stages)
            _criteria(task)
            active = next((stage for stage in stages if stage["status"] in {"available", "revision", "pending"}), None)
            if active is None:
                st.success(f"Результат принят. Все три этапа подтверждены, получено {PROJECT_XP} XP за проект.")
            elif active["status"] == "pending":
                st.info(f"{STAGE_TITLES[active['id']]} на проверке у бизнеса. Сейчас отправлять ничего не нужно.")
                with st.expander("Посмотреть отправленный результат"):
                    _show_evidence(active["submission"])
            else:
                _render_stage_form(task, team, active)
            _history(stages)


def _render_stage_form(task: dict[str, Any], team: dict[str, Any], stage: dict[str, Any]) -> None:
    row = stage.get("submission") or {}
    st.markdown(f"### Подготовьте {STAGE_TITLES[stage['id']].lower()}")
    st.write(stage["description"])
    if stage["status"] == "revision":
        st.warning("Бизнес вернул этап на доработку. Обновите результат по комментарию и отправьте снова.")
        st.markdown("**Что нужно доработать**")
        st.write(row.get("feedback", ""))
    form_id = f"stage_{task['id']}_{team['id']}_{stage['id']}"
    evidence_key = f"{form_id}_evidence"
    url_key = f"{form_id}_url"
    if evidence_key not in st.session_state:
        st.session_state[evidence_key] = row.get("evidence", "")
    if url_key not in st.session_state:
        st.session_state[url_key] = row.get("url", "")
    with st.form(form_id):
        evidence = st.text_area(
            "Что сделано и как проверено", key=evidence_key, height=130, max_chars=4000,
            help="Опишите конкретный результат и его проверку (от 20 символов). Бизнес увидит этот отчёт перед подтверждением.",
            placeholder="Что подготовили, как проверили и какой получили результат?",
        )
        url = st.text_input("Ссылка на результат (необязательно)", key=url_key, max_chars=2048, placeholder="https://…")
        submitted = st.form_submit_button("Отправить этап на проверку", type="primary")
    if submitted:
        try:
            updated = submit_stage(
                st.session_state.tasks, st.session_state.applications, _submissions(),
                task["id"], team["id"], stage["id"], evidence, url,
            )
        except ValueError as error:
            st.error(str(error))
        else:
            st.session_state.submissions = updated
            st.session_state[f"progress_notice_team_{team['id']}"] = "Этап отправлен на проверку. Ожидайте решения бизнеса."
            st.rerun()


def render_team_applications(team: dict[str, Any]) -> None:
    page_header("ПРЕДЛОЖЕНИЯ КОМАНДЫ", "Мои отклики", "Здесь видны решения бизнеса по вашим предложениям.")
    applications = [app for app in st.session_state.applications if app.get("team_id") == team["id"]]
    applications.sort(key=lambda app: app.get("created_at", ""), reverse=True)
    if not applications:
        st.info("У команды пока нет откликов. Найдите интересную задачу и предложите свой подход.")
        st.button("Найти задачу в каталоге", key=f"applications_browse_{team['id']}", on_click=_open_team_page, args=("Каталог",), type="primary")
        return
    tasks = {task["id"]: task for task in st.session_state.tasks}
    for application in applications:
        task = tasks.get(application.get("task_id"), {})
        with st.container(border=True):
            st.subheader(task.get("title") or "Задача недоступна")
            status = application.get("status", "pending")
            status_badge(APPLICATION_LABELS.get(status, "На рассмотрении"), STATUS_TONES.get(status, "neutral"))
            st.caption(f"Бизнес: {task.get('owner_id', '')} · {format_date(application.get('created_at', ''))}")
            st.markdown("**Идея решения**")
            st.write(application.get("idea", ""))
            with st.expander("План и прототип"):
                st.write(application.get("plan", ""))
                _safe_link(application.get("prototype_url", ""), "Открыть прототип")
            if status == "selected":
                st.success("Можно приступать к работе. Следующий шаг — в проекте.")
                st.button("Перейти к этапам проекта", key=f"application_project_{application['id']}", on_click=_open_team_page, args=("Мои проекты",), type="primary")
            elif status == "pending":
                st.caption("Предложение отправлено. Дождитесь решения бизнеса.")
            else:
                st.caption("Можно предложить другой подход или выбрать новую задачу в каталоге.")


def render_business_progress(task: dict[str, Any], owner_id: str) -> None:
    if not owner_id or task.get("owner_id") != owner_id:
        return
    selected_ids = {
        app["team_id"] for app in st.session_state.applications
        if app.get("task_id") == task["id"] and app.get("status") == "selected" and app.get("team_id")
    }
    if not selected_ids:
        return
    st.markdown("### Результаты команд")
    st.caption("Примите готовый этап или верните его с комментарием о доработке.")
    _notice(f"progress_notice_business_{task['id']}")
    teams = {team["id"]: team for team in st.session_state.teams}
    for team_id in sorted(selected_ids):
        with st.container(border=True):
            name = teams.get(team_id, {}).get("name") or next(
                (app.get("team_name", "Команда") for app in st.session_state.applications if app.get("team_id") == team_id), "Команда",
            )
            st.markdown(f"**{name}**")
            stages = project_stages(_submissions(), task["id"], team_id)
            _roadmap(stages)
            pending = next((stage for stage in stages if stage["status"] == "pending"), None)
            if pending:
                _render_review_form(task, owner_id, pending)
            elif all(stage["status"] == "approved" for stage in stages):
                st.success("Работа по задаче завершена: результат принят бизнесом.")
            elif any(stage["status"] == "revision" for stage in stages):
                st.warning("Команда дорабатывает этап. Новая версия появится здесь после отправки.")
            else:
                st.info("Ожидаем результат команды. Когда она отправит этап, здесь появится форма проверки.")
            _history(stages)


def _render_review_form(task: dict[str, Any], owner_id: str, stage: dict[str, Any]) -> None:
    row = stage["submission"]
    st.markdown(f"#### Проверьте {STAGE_TITLES[stage['id']].lower()}")
    _show_evidence(row)
    _criteria(task)
    form_id = f"review_{row['id']}"
    with st.form(form_id):
        feedback = st.text_area(
            "Обратная связь команде", key=f"{form_id}_feedback", height=90, max_chars=2000,
            help="Для доработки укажите, что нужно изменить (минимум 5 символов). При подтверждении комментарий необязателен.",
            placeholder="Необязательно при принятии. Для доработки напишите, что нужно изменить.",
        )
        st.caption(f"Принятый этап принесёт команде {stage['xp']} XP — баллов опыта.")
        accept_col, revise_col = st.columns(2)
        accepted = accept_col.form_submit_button(f"Подтвердить этап · +{stage['xp']} XP", type="primary")
        revised = revise_col.form_submit_button("Вернуть на доработку")
    if accepted or revised:
        try:
            updated = review_stage(
                st.session_state.tasks, st.session_state.applications, _submissions(), owner_id,
                row["id"], "approve" if accepted else "revise", feedback,
            )
        except ValueError as error:
            st.error(str(error))
        else:
            st.session_state.submissions = updated
            st.session_state[f"progress_notice_business_{task['id']}"] = (
                f"Этап подтверждён. Команде начислено {stage['xp']} XP."
                if accepted else "Этап возвращён на доработку с вашей обратной связью."
            )
            st.rerun()
