"""Streamlit views for work confirmed by business and the team's earned XP."""

from __future__ import annotations

from typing import Any

import streamlit as st

from src.models import is_valid_prototype_url
from src.progress import MILESTONES, project_stages, review_stage, submit_stage, team_summary


PROJECT_XP = sum(stage["xp"] for stage in MILESTONES)
STAGE_LABELS = {
    "available": "Можно отправить",
    "locked": "После предыдущего этапа",
    "pending": "На проверке у бизнеса",
    "revision": "Нужна доработка",
    "approved": "Подтверждено бизнесом",
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
    st.progress(earned / PROJECT_XP, text=f"Подтверждено: {earned} из {PROJECT_XP} XP за проект")
    for index, (column, stage) in enumerate(zip(st.columns(len(stages)), stages), start=1):
        with column:
            st.markdown(f"**{index}. {stage['title']}**")
            st.caption(STAGE_LABELS[stage["status"]])
            label = "Начислено" if stage["status"] == "approved" else "За подтверждение"
            st.caption(f"{label}: {stage['xp']} XP")
    return earned


def _show_evidence(row: dict[str, Any]) -> None:
    st.markdown("**Что сделано и как проверено**")
    st.write(row.get("evidence", ""))
    _safe_link(row.get("url", ""))
    st.caption(f"Попытка {row.get('attempt', 1)} · отправлено {row.get('submitted_at', '')}")


def _history(stages: list[dict[str, Any]]) -> None:
    recorded = [stage for stage in stages if stage.get("submission")]
    if not recorded:
        return
    with st.expander("История этапов и решений"):
        for stage in recorded:
            current = stage["submission"]
            for row in [*current.get("history", []), current]:
                st.markdown(f"**{stage['title']} · попытка {row.get('attempt', 1)}**")
                st.caption(STAGE_LABELS.get(row.get("status", ""), "Отправлено"))
                _show_evidence(row)
                if row.get("reviewed_at"):
                    st.caption(f"Решение: {row['reviewed_at']} · {row.get('reviewed_by', '')}")
                if row.get("feedback"):
                    st.markdown("**Обратная связь бизнеса**")
                    st.write(row["feedback"])
                if row.get("status") == "approved":
                    st.caption(f"Начислено {stage['xp']} XP один раз за этот этап.")
                st.divider()


def _criteria(task: dict[str, Any]) -> None:
    criteria = str(task.get("success_criteria", "") or "").strip()
    if criteria:
        st.markdown("**Критерии успеха из подтверждённой карточки**")
        st.write(criteria)
    else:
        st.info("В карточке ещё нет критериев успеха. Согласуйте их с бизнесом и опишите в первом этапе.")


def render_team_dashboard(team: dict[str, Any]) -> None:
    summary = team_summary(_submissions(), team["id"])
    st.subheader(f"Маршрут команды · {team['name']}")
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
    st.caption(
        f"За один проект можно получить {PROJECT_XP} XP: план 20, прототип 40, результат 60. "
        "Баллы появляются после подтверждения этапа бизнесом. Отклики и выбор команды XP не дают. "
        "Рейтинг задачи 0–100 оценивает её готовность отдельно от опыта команды."
    )
    if summary["badges"]:
        st.markdown("**Достижения**")
        for badge in summary["badges"]:
            st.write(f"✓ {badge}")
    else:
        st.caption("Первое достижение откроется после подтверждения плана бизнесом.")


def render_team_projects(team: dict[str, Any]) -> None:
    st.header("Мои проекты")
    _notice(f"progress_notice_team_{team['id']}")
    selected_ids = {
        app["task_id"] for app in st.session_state.applications
        if app.get("team_id") == team["id"] and app.get("status") == "selected"
    }
    tasks = [task for task in st.session_state.tasks if task.get("id") in selected_ids and task.get("status") == "published"]
    if not tasks:
        st.info("Здесь появятся задачи, для которых бизнес выбрал вашу команду. Откройте каталог, отправьте предложение и дождитесь ручного выбора бизнеса.")
        st.button("Перейти в каталог", key=f"projects_browse_{team['id']}", on_click=_open_team_page, args=("Каталог",), type="primary")
        return
    st.caption("Сдавайте этапы по порядку. После доработки можно отправить обновлённый результат; предыдущая версия остаётся в истории.")
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
                st.info(f"«{active['title']}» отправлен бизнесу. XP начислятся после подтверждения.")
                _show_evidence(active["submission"])
            else:
                _render_stage_form(task, team, active)
            _history(stages)


def _render_stage_form(task: dict[str, Any], team: dict[str, Any], stage: dict[str, Any]) -> None:
    row = stage.get("submission") or {}
    st.markdown(f"### Следующий этап: {stage['title']}")
    st.write(stage["description"])
    if stage["status"] == "revision":
        st.warning("Бизнес вернул этап на доработку. XP пока не начислены.")
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
    st.header("Мои отклики")
    applications = [app for app in st.session_state.applications if app.get("team_id") == team["id"]]
    applications.sort(key=lambda app: app.get("created_at", ""), reverse=True)
    if not applications:
        st.info("У команды пока нет откликов. В каталоге можно предложить решение любой опубликованной задачи, включая задачи с низким рейтингом.")
        st.button("Найти задачу в каталоге", key=f"applications_browse_{team['id']}", on_click=_open_team_page, args=("Каталог",), type="primary")
        return
    st.caption("Каждое предложение показано отдельно. Бизнес может выбрать одну, несколько или ни одной команды.")
    tasks = {task["id"]: task for task in st.session_state.tasks}
    for application in applications:
        task = tasks.get(application.get("task_id"), {})
        with st.container(border=True):
            st.subheader(task.get("title") or "Задача недоступна")
            status = application.get("status", "pending")
            st.markdown(f"**{APPLICATION_LABELS.get(status, 'На рассмотрении')}**")
            st.caption(f"Бизнес: {task.get('owner_id', '')} · отправлено {application.get('created_at', '')}")
            st.markdown("**Идея решения**")
            st.write(application.get("idea", ""))
            st.markdown("**План работы**")
            st.write(application.get("plan", ""))
            _safe_link(application.get("prototype_url", ""), "Открыть прототип")
            if status == "selected":
                st.success("Бизнес выбрал команду. Перейдите в «Мои проекты», чтобы отправить первый этап.")
                st.button("Перейти к этапам проекта", key=f"application_project_{application['id']}", on_click=_open_team_page, args=("Мои проекты",))


def render_business_progress(task: dict[str, Any], owner_id: str) -> None:
    if not owner_id or task.get("owner_id") != owner_id:
        return
    selected_ids = {
        app["team_id"] for app in st.session_state.applications
        if app.get("task_id") == task["id"] and app.get("status") == "selected" and app.get("team_id")
    }
    if not selected_ids:
        return
    st.markdown("### Подтверждение результатов")
    st.caption("Сравните отчёт с критериями задачи. Подтверждение начислит фиксированные XP команде; отправка на доработку сохранит обратную связь.")
    _notice(f"progress_notice_business_{task['id']}")
    _criteria(task)
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
                st.info("Команда дорабатывает этап. Новая версия появится после повторной отправки.")
            else:
                st.caption("Ожидается отчёт команды по следующему этапу.")
            _history(stages)


def _render_review_form(task: dict[str, Any], owner_id: str, stage: dict[str, Any]) -> None:
    row = stage["submission"]
    st.markdown(f"**На проверке: {stage['title']}**")
    _show_evidence(row)
    form_id = f"review_{row['id']}"
    with st.form(form_id):
        feedback = st.text_area(
            "Обратная связь команде", key=f"{form_id}_feedback", height=90, max_chars=2000,
            help="Для доработки укажите, что нужно изменить (минимум 5 символов). При подтверждении комментарий необязателен.",
        )
        st.caption(f"Подтверждая этап, вы принимаете описанный результат и начисляете {stage['xp']} XP один раз.")
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
