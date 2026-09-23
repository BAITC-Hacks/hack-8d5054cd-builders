from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import streamlit as st

from src.ai import DEMO_ANSWERS, DEMO_DRAFT, DEMO_MODE, analyze_draft, build_card
from src.models import CARD_FIELDS, Application, TaskCard, make_id, utc_now
from src.rating import calculate_rating


ROOT = Path(__file__).resolve().parent
SEED_PATH = ROOT / "data" / "seed.json"

st.set_page_config(
    page_title="HackAlem AI · Практикум",
    page_icon="🧩",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
      .block-container {padding-top: 2rem; padding-bottom: 3rem; max-width: 1240px;}
      [data-testid="stMetricValue"] {font-weight: 750;}
      .stProgress > div > div > div > div {background-color: #14b8a6;}
      div[data-testid="stAlert"] {border-radius: 12px;}
    </style>
    """,
    unsafe_allow_html=True,
)


def _load_seed() -> dict[str, Any]:
    with SEED_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def initialize_state() -> None:
    if "initialized" in st.session_state:
        return
    seed = _load_seed()
    st.session_state.tasks = deepcopy(seed["cards"])
    st.session_state.applications = deepcopy(seed["applications"])
    st.session_state.teams = deepcopy(seed["teams"])
    st.session_state.seed_drafts = deepcopy(seed["drafts"])
    for task in st.session_state.tasks:
        task["rating"] = calculate_rating(task)["score"]
    st.session_state.initialized = True
    st.session_state.business_identity = "Alem Retail"
    st.session_state.role = "Бизнес"
    st.session_state.draft_text = ""
    st.session_state.analysis = None
    st.session_state.analysis_draft = None
    st.session_state.draft_card = None
    st.session_state.card_source_mode = ""


def _show_ai_mode() -> None:
    if DEMO_MODE:
        st.caption("AI: включён локальный демо-сценарий")
    elif not os.getenv("OPENAI_API_KEY", "").strip():
        st.caption("AI: локальная заглушка (задайте OPENAI_API_KEY для вызова модели)")
    else:
        st.caption("AI: OpenAI · при сетевой ошибке включится локальная заглушка")


def _reset_builder() -> None:
    for key in list(st.session_state.keys()):
        if key.startswith("answer_") or key.startswith("editor_"):
            st.session_state.pop(key, None)
    st.session_state.draft_text = ""
    st.session_state.analysis = None
    st.session_state.analysis_draft = None
    st.session_state.draft_card = None
    st.session_state.card_source_mode = ""


def _rating_panel(card: dict[str, Any], *, compact: bool = False) -> dict[str, Any]:
    result = calculate_rating(card)
    left, middle, right = st.columns([1, 2, 3])
    left.metric("Рейтинг", f"{result['score']} / 100")
    middle.metric("Уровень готовности", result["level"])
    right.progress(result["score"] / 100)

    with st.expander("Из чего складывается рейтинг", expanded=False):
        for row in result["breakdown"]:
            st.write(f"**{row['label']}** — {row['earned']} из {row['possible']} баллов")
        st.caption("Короткий ответ даёт целочисленную половину веса (округление вниз); подробный ответ — полный вес.")
        st.caption("Пороги подробности: контекст 35, потребность 20, данные 15, результат и критерии 20, ограничения 14, пользователи 10, контакт 5, формат 12 символов.")

    if result["improvements"]:
        st.markdown("**Что повысит рейтинг**")
        for item in result["improvements"][:5 if compact else 9]:
            st.write(f"+{item['potential_points']} · **{item['label']}** — {item['hint']}")
    elif not compact:
        st.success("Все оцениваемые поля заполнены достаточно подробно.")
    return result


def _render_task_contents(task: dict[str, Any]) -> None:
    for field, label in CARD_FIELDS.items():
        value = str(task.get(field, "") or "").strip()
        if value:
            st.markdown(f"**{label}**  \n{value}")
        elif field != "title":
            st.markdown(f"**{label}**  \n_Пока не указано_")


def _application_count(task_id: str) -> int:
    return sum(1 for app in st.session_state.applications if app.get("task_id") == task_id)


def _set_application_status(application_id: str, status: str) -> None:
    for application in st.session_state.applications:
        if application.get("id") == application_id:
            application["status"] = status
            return


def render_new_task(owner_id: str) -> None:
    st.header("Новая задача")
    st.write("Опишите бизнес-потребность. AI поможет найти пробелы, а публикация произойдёт только после вашего подтверждения.")

    sample_col, reset_col, _ = st.columns([1.4, 1.0, 2.2])
    if sample_col.button("Вставить пример для демо", use_container_width=True, help="Сценарий про незавершённые онлайн-заказы"):
        _reset_builder()
        st.session_state.draft_text = DEMO_DRAFT
        st.session_state.use_demo_answers = True
    if reset_col.button("Очистить", use_container_width=True):
        _reset_builder()
        st.session_state.use_demo_answers = False

    with st.form("draft_analysis_form"):
        draft = st.text_area(
            "Черновик задачи",
            key="draft_text",
            height=130,
            placeholder="Например: покупатели часто оставляют корзины на сайте; хотим понять причины и улучшить оформление заказа.",
        )
        submitted = st.form_submit_button("Проанализировать", type="primary")

    if submitted:
        if not draft.strip():
            st.warning("Добавьте хотя бы краткое описание задачи.")
        else:
            result = analyze_draft(draft.strip())
            st.session_state.analysis = result
            st.session_state.analysis_draft = draft.strip()
            st.session_state.draft_card = None
            st.session_state.card_source_mode = ""
            use_sample_answers = (
                bool(st.session_state.get("use_demo_answers"))
                and draft.strip() == DEMO_DRAFT.strip()
            )
            for index, question in enumerate(result["questions"]):
                field = question["field"]
                answer_key = f"answer_{index}_{field}"
                st.session_state[answer_key] = DEMO_ANSWERS.get(field, "") if use_sample_answers else ""

    analysis = st.session_state.get("analysis")
    current_draft = str(st.session_state.get("draft_text", "")).strip()
    if analysis and current_draft == st.session_state.get("analysis_draft"):
        if analysis.get("mode") == "demo":
            st.info("Для этого шага используется локальный демо-сценарий. Он работает без API-ключа и сети.")
        else:
            st.success("Черновик проанализирован. Проверьте ответы и дополните их фактами бизнеса.")

        missing = analysis.get("missing_fields", [])
        if missing:
            labels = [CARD_FIELDS[field] for field in missing if field in CARD_FIELDS]
            if labels:
                st.caption("Нужно уточнить: " + ", ".join(labels))

        baseline_card = {field: "" for field in CARD_FIELDS}
        baseline_card["context"] = current_draft
        baseline = calculate_rating(baseline_card)
        st.markdown("### Стартовая готовность до уточнений")
        st.metric("Рейтинг черновика", f"{baseline['score']} / 100")
        st.caption(f"Уровень: {baseline['level']}")
        st.markdown("**Что повысит рейтинг**")
        for item in baseline["improvements"][:4]:
            st.write(f"+{item['potential_points']} · **{item['label']}** — {item['hint']}")

        with st.form("clarification_form"):
            st.subheader("Уточняющие вопросы")
            for index, question in enumerate(analysis["questions"]):
                field = question["field"]
                st.text_area(
                    question["question"],
                    key=f"answer_{index}_{field}",
                    height=90,
                )
            build_submitted = st.form_submit_button("Сформировать карточку", type="primary")

        if build_submitted:
            answers_by_field: dict[str, list[str]] = {}
            for index, question in enumerate(analysis["questions"]):
                answer = str(st.session_state.get(f"answer_{index}_{question['field']}", "")).strip()
                if answer:
                    answers_by_field.setdefault(question["field"], []).append(answer)
            answers = {key: "\n".join(values) for key, values in answers_by_field.items()}
            generated = build_card(current_draft, answers)
            st.session_state.draft_card = generated["card"]
            st.session_state.card_source_mode = generated["mode"]
            for field in CARD_FIELDS:
                st.session_state[f"editor_{field}"] = generated["card"].get(field, "")

        if st.session_state.get("draft_card"):
            st.divider()
            st.subheader("Проверьте и отредактируйте карточку")
            st.caption("Баллы пересчитываются при каждом изменении. Публикация требует отдельного подтверждения.")
            if st.session_state.get("card_source_mode") == "demo":
                st.info("Карточка собрана локально только из черновика и ваших ответов.")
            candidate: dict[str, str] = {}
            field_columns = st.columns(2)
            fields = list(CARD_FIELDS.items())
            for index, (field, label) in enumerate(fields):
                column = field_columns[index % 2]
                key = f"editor_{field}"
                if key not in st.session_state:
                    st.session_state[key] = st.session_state.draft_card.get(field, "")
                with column:
                    if field == "title":
                        st.text_input(label, key=key)
                    else:
                        st.text_area(label, key=key, height=110)
                candidate[field] = str(st.session_state.get(key, ""))

            st.markdown("### Текущий рейтинг")
            current_rating = _rating_panel(candidate)
            if st.button("Подтвердить и опубликовать", type="primary", key="publish_task"):
                if not candidate.get("title", "").strip():
                    st.error("Перед публикацией укажите название задачи.")
                else:
                    card = TaskCard.from_dict(candidate).to_dict()
                    card.update(
                        id=make_id("task"),
                        owner_id=owner_id,
                        status="published",
                        created_at=utc_now(),
                        rating=current_rating["score"],
                    )
                    st.session_state.tasks.insert(0, card)
                    st.session_state.draft_card = None
                    st.success("Задача опубликована в общем каталоге. Команды могут откликаться при любом рейтинге.")
                    st.balloons()


def render_application(task: dict[str, Any], team: dict[str, Any]) -> None:
    task_id = task["id"]
    with st.expander("Откликнуться на задачу", expanded=False):
        with st.form(f"application_form_{task_id}"):
            team_key = f"apply_team_{task_id}"
            if team_key not in st.session_state:
                st.session_state[team_key] = team["name"]
            st.text_input("Название команды", key=team_key)
            st.text_area("Идея решения", key=f"apply_idea_{task_id}", height=100)
            st.text_area("План работы", key=f"apply_plan_{task_id}", height=100)
            st.text_input(
                "Ссылка на прототип (необязательно)",
                key=f"apply_url_{task_id}",
                placeholder="https://...",
            )
            submitted = st.form_submit_button("Отправить отклик", type="primary")
        if submitted:
            team_name = str(st.session_state.get(f"apply_team_{task_id}", "")).strip()
            idea = str(st.session_state.get(f"apply_idea_{task_id}", "")).strip()
            plan = str(st.session_state.get(f"apply_plan_{task_id}", "")).strip()
            url = str(st.session_state.get(f"apply_url_{task_id}", "")).strip()
            if not team_name or not idea or not plan:
                st.error("Укажите название команды, идею и план работы.")
            elif url and urlparse(url).scheme not in {"http", "https"}:
                st.error("Ссылка на прототип должна начинаться с http:// или https://.")
            else:
                application = Application(
                    task_id=task_id,
                    team_name=team_name,
                    idea=idea,
                    plan=plan,
                    prototype_url=url,
                ).to_dict()
                st.session_state.applications.append(application)
                st.success("Отклик отправлен бизнесу.")


def render_catalog(team: dict[str, Any]) -> None:
    st.header("Открытый каталог")
    st.write("Опубликованные задачи отсортированы по рейтингу. Даже черновик с низким баллом открыт для откликов.")
    tasks = [task for task in st.session_state.tasks if task.get("status") == "published"]
    tasks.sort(key=lambda task: (calculate_rating(task)["score"], task.get("created_at", "")), reverse=True)
    if not tasks:
        st.info("Пока нет опубликованных задач.")
        return

    for task in tasks:
        rating = calculate_rating(task)
        with st.container(border=True):
            head, score_col = st.columns([4, 1])
            head.subheader(task.get("title") or "Задача без названия")
            head.caption(f"Бизнес: {task.get('owner_id') or 'Не указано'} · {_application_count(task['id'])} откликов")
            score_col.metric("Рейтинг", f"{rating['score']} / 100")
            score_col.caption(rating["level"])
            st.progress(rating["score"] / 100)
            with st.expander("Посмотреть карточку"):
                _render_task_contents(task)
                _rating_panel(task, compact=True)
            render_application(task, team)


def _render_edit_form(task: dict[str, Any]) -> None:
    notice_key = f"edit_notice_{task['id']}"
    with st.expander("Редактировать опубликованную карточку"):
        with st.form(f"edit_task_{task['id']}"):
            for field, label in CARD_FIELDS.items():
                key = f"edit_{task['id']}_{field}"
                if key not in st.session_state:
                    st.session_state[key] = str(task.get(field, "") or "")
                if field == "title":
                    st.text_input(label, key=key)
                else:
                    st.text_area(label, key=key, height=90)
            submitted = st.form_submit_button("Сохранить изменения и пересчитать рейтинг")
        if submitted:
            updated = {field: str(st.session_state.get(f"edit_{task['id']}_{field}", "")) for field in CARD_FIELDS}
            if not updated["title"].strip():
                st.error("Название карточки не может быть пустым.")
            else:
                task.update(updated)
                task["rating"] = calculate_rating(task)["score"]
                st.session_state[notice_key] = f"Изменения подтверждены. Новый рейтинг: {task['rating']} / 100."
                st.rerun()
    if st.session_state.get(notice_key):
        st.success(st.session_state.pop(notice_key))


def _render_applications(task: dict[str, Any]) -> None:
    applications = [app for app in st.session_state.applications if app.get("task_id") == task["id"]]
    st.markdown(f"**Отклики ({len(applications)})**")
    if not applications:
        st.caption("Пока откликов нет.")
        return
    for application in applications:
        with st.container(border=True):
            left, status_col = st.columns([4, 1])
            left.markdown(f"**{application.get('team_name', 'Команда')}**")
            status_labels = {"pending": "На рассмотрении", "selected": "Выбрана", "rejected": "Отклонена"}
            status_col.caption(status_labels.get(application.get("status", "pending"), "На рассмотрении"))
            left.markdown(f"**Идея:** {application.get('idea', '')}")
            left.markdown(f"**План:** {application.get('plan', '')}")
            prototype = application.get("prototype_url", "")
            if prototype:
                left.markdown(f"[Открыть прототип]({prototype})")
            if application.get("status") == "pending":
                choose_col, reject_col, _ = st.columns([1, 1, 4])
                choose_col.button(
                    "Выбрать",
                    key=f"choose_{application['id']}",
                    type="primary",
                    on_click=_set_application_status,
                    args=(application["id"], "selected"),
                )
                reject_col.button(
                    "Отклонить",
                    key=f"reject_{application['id']}",
                    on_click=_set_application_status,
                    args=(application["id"], "rejected"),
                )


def render_my_tasks(owner_id: str) -> None:
    st.header("Мои задачи")
    st.caption("В этом демо имя бизнеса задаёт рабочее пространство; авторизации нет.")
    tasks = [
        task for task in st.session_state.tasks
        if task.get("owner_id") == owner_id and task.get("status") == "published"
    ]
    tasks.sort(key=lambda task: task.get("created_at", ""), reverse=True)
    if not tasks:
        st.info("У этого бизнеса пока нет опубликованных задач. Создайте карточку во вкладке «Новая задача».")
        return
    for task in tasks:
        rating = calculate_rating(task)
        with st.container(border=True):
            title_col, metric_col = st.columns([4, 1])
            title_col.subheader(task.get("title") or "Задача без названия")
            title_col.caption(f"{rating['level']} · { _application_count(task['id']) } откликов")
            metric_col.metric("Рейтинг", f"{rating['score']} / 100")
            st.progress(rating["score"] / 100)
            _render_edit_form(task)
            _render_applications(task)


def render_sidebar() -> tuple[str, str, dict[str, Any] | None]:
    st.sidebar.title("HackAlem AI")
    st.sidebar.caption("Практикум бизнес-задач")
    role = st.sidebar.radio("Роль", ["Бизнес", "Студенческая команда"], key="role")
    st.sidebar.divider()
    if role == "Бизнес":
        owner_id = st.sidebar.text_input("Рабочее пространство бизнеса", key="business_identity")
        if not owner_id.strip():
            owner_id = "Alem Retail"
            st.sidebar.caption("Укажите имя компании, чтобы видеть её задачи.")
        st.sidebar.caption("Имя используется для списка «Мои задачи», это не аккаунт.")
        team = None
    else:
        teams = st.session_state.teams
        names = [item["name"] for item in teams]
        team_name = st.sidebar.selectbox("Выберите команду", names, key="active_team")
        team = next(item for item in teams if item["name"] == team_name)
        st.sidebar.markdown("**Интересы**  \n" + ", ".join(team.get("interests", [])))
        st.sidebar.markdown("**Навыки**  \n" + ", ".join(team.get("skills", [])))
        st.sidebar.markdown("**Технологии**  \n" + ", ".join(team.get("technologies", [])))
        owner_id = ""
    st.sidebar.divider()
    _show_ai_mode()
    return role, owner_id.strip(), team


def main() -> None:
    initialize_state()
    role, owner_id, team = render_sidebar()
    st.title("Задачи бизнеса. Выбор за командами.")
    st.caption("Опишите задачу, повысьте её готовность и работайте с откликами напрямую.")

    if role == "Бизнес":
        new_tab, my_tab = st.tabs(["Новая задача", "Мои задачи"])
        with new_tab:
            render_new_task(owner_id)
        with my_tab:
            render_my_tasks(owner_id)
    else:
        assert team is not None
        render_catalog(team)


if __name__ == "__main__":
    main()
