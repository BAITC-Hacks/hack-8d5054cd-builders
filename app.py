from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import streamlit as st

from src.ai import DEMO_ANSWERS, DEMO_DRAFT, ERROR_LABELS, PROVIDER_LABELS, analyze_draft, build_card, check_connection
from src.config import get_settings
from src.models import CARD_FIELDS, Application, TaskCard, is_valid_prototype_url, make_id, utc_now
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
    settings = get_settings()
    with st.sidebar.expander("AI и подключение", expanded=True):
        if st.button("Перечитать .env", key="reload_ai_settings"):
            st.session_state.ai_provider = "demo" if settings["demo"] else settings["provider"]
            st.session_state.pop("connection_result", None)
        if "ai_provider" not in st.session_state:
            st.session_state.ai_provider = "demo" if settings["demo"] else settings["provider"]
        selected = st.selectbox(
            "Источник AI", ["auto", "openai", "nvidia", "demo"],
            format_func=lambda value: PROVIDER_LABELS[value], key="ai_provider",
        )
        for name in ("openai", "nvidia"):
            status = "ключ добавлен" if settings[f"{name}_ready"] else "ключ не добавлен"
            st.caption(f"{PROVIDER_LABELS[name]}: {status}")
            if settings[f"{name}_ready"]:
                st.caption(settings[f"{name}_model"])
        if selected == "auto":
            st.caption("При сбое OpenAI попробуем NVIDIA, затем локальную сборку.")
        if st.button("Проверить подключение", disabled=selected == "demo", help="Короткий запрос к выбранному API; расходует несколько токенов."):
            with st.spinner("Проверяем доступ к модели…"):
                st.session_state.connection_result = check_connection(selected)
        for item in st.session_state.get("connection_result", {}).get("results", []):
            label = PROVIDER_LABELS[item["provider"]]
            if item["ok"]:
                st.success(f"{label}: запрос выполнен")
            else:
                st.warning(f"{label}: {ERROR_LABELS[item['reason']]}")
        st.caption("Ключи добавляются в локальный .env. Их значения здесь не отображаются.")


def _show_ai_result(result: dict[str, Any]) -> None:
    mode = result.get("mode", "demo")
    if mode == "demo":
        if result.get("reason") == "demo_requested":
            st.info("Используется локальный сценарий без обращения к API.")
        else:
            st.warning("Использована локальная сборка: доступный AI не вернул проверенный результат.")
    else:
        st.success(f"{PROVIDER_LABELS[mode]} · {result.get('model', '')}: ответ проверен по исходному тексту.")
    for attempt in result.get("attempts", []):
        st.caption(f"{PROVIDER_LABELS[attempt['provider']]}: {ERROR_LABELS[attempt['reason']]}")


def _reset_builder() -> None:
    for key in list(st.session_state.keys()):
        if key.startswith("answer_") or key.startswith("editor_"):
            st.session_state.pop(key, None)
    st.session_state.draft_text = ""
    st.session_state.analysis = None
    st.session_state.analysis_draft = None
    st.session_state.draft_card = None
    st.session_state.card_source_mode = ""
    st.session_state.pop("card_result", None)
    st.session_state.pop("builder_answers", None)


def _rating_panel(card: dict[str, Any], *, compact: bool = False) -> dict[str, Any]:
    result = calculate_rating(card)
    left, middle, right = st.columns([1, 2, 3])
    left.metric("Рейтинг", f"{result['score']} / 100")
    middle.metric("Уровень готовности", result["level"])
    right.progress(result["score"] / 100)

    with st.expander("Из чего складывается рейтинг", expanded=False):
        for row in result["breakdown"]:
            st.write(f"**{row['label']}** — {row['earned']} из {row['possible']} баллов")
        st.caption("Это рейтинг заполненности, не экспертиза решения. Пустые поля, известные заглушки и явный мусор дают 0; короткий ответ — половину веса с округлением вниз.")
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
            max_chars=8000,
            placeholder="Например: покупатели часто оставляют корзины на сайте; хотим понять причины и улучшить оформление заказа.",
        )
        submitted = st.form_submit_button("Проанализировать", type="primary")

    if submitted:
        if not draft.strip():
            st.warning("Добавьте хотя бы краткое описание задачи.")
        else:
            with st.spinner("Находим сведения и уточняющие вопросы…"):
                result = analyze_draft(draft.strip(), provider=st.session_state.ai_provider)
            st.session_state.analysis = result
            st.session_state.analysis_draft = draft.strip()
            st.session_state.draft_card = None
            st.session_state.card_source_mode = ""
            st.session_state.pop("card_result", None)
            st.session_state.builder_answers = {}
            use_sample_answers = (
                bool(st.session_state.get("use_demo_answers"))
                and draft.strip() == DEMO_DRAFT.strip()
            )
            for index, question in enumerate(result["questions"]):
                field = question["field"]
                answer_key = f"answer_{index}_{field}"
                st.session_state[answer_key] = DEMO_ANSWERS.get(field, "") if use_sample_answers else ""
                st.session_state.builder_answers[answer_key] = st.session_state[answer_key]

    analysis = st.session_state.get("analysis")
    current_draft = str(st.session_state.get("draft_text", "")).strip()
    if analysis and current_draft == st.session_state.get("analysis_draft"):
        _show_ai_result(analysis)

        missing = analysis.get("missing_fields", [])
        if missing:
            labels = [CARD_FIELDS[field] for field in missing if field in CARD_FIELDS]
            if labels:
                st.caption("Нужно уточнить: " + ", ".join(labels))

        baseline_card = analysis.get("card") or {"context": current_draft}
        baseline = calculate_rating(baseline_card)
        st.markdown("### Предварительная полнота черновика")
        st.metric("Рейтинг черновика", f"{baseline['score']} / 100")
        st.caption(f"Уровень: {baseline['level']}")
        if analysis.get("baseline_quality") != "extracted":
            st.caption("Локально распознаются явные поля вида «Данные: …». Свободный текст учитывается как контекст; оценка может быть занижена.")
        with st.expander("Какие сведения найдены в черновике"):
            _render_task_contents(baseline_card)
        st.markdown("**Что повысит рейтинг**")
        for item in baseline["improvements"][:4]:
            st.write(f"+{item['potential_points']} · **{item['label']}** — {item['hint']}")

        with st.form("clarification_form"):
            st.subheader("Уточняющие вопросы")
            for index, question in enumerate(analysis["questions"]):
                field = question["field"]
                answer_key = f"answer_{index}_{field}"
                if answer_key not in st.session_state:
                    st.session_state[answer_key] = st.session_state.get("builder_answers", {}).get(answer_key, "")
                st.text_area(
                    question["question"],
                    key=f"answer_{index}_{field}",
                    height=90,
                    max_chars=2000,
                )
            build_submitted = st.form_submit_button("Сформировать карточку", type="primary")

        if build_submitted:
            answers_by_field: dict[str, list[str]] = {}
            for index, question in enumerate(analysis["questions"]):
                answer = str(st.session_state.get(f"answer_{index}_{question['field']}", "")).strip()
                st.session_state.setdefault("builder_answers", {})[f"answer_{index}_{question['field']}"] = answer
                if answer:
                    answers_by_field.setdefault(question["field"], []).append(answer)
            answers = {key: "\n".join(values) for key, values in answers_by_field.items()}
            with st.spinner("Собираем карточку и проверяем источники фактов…"):
                generated = build_card(current_draft, answers, provider=st.session_state.ai_provider, known_card=baseline_card)
            st.session_state.draft_card = generated["card"]
            st.session_state.card_source_mode = generated["mode"]
            st.session_state.card_result = generated
            for field in CARD_FIELDS:
                st.session_state[f"editor_{field}"] = generated["card"].get(field, "")

        if st.session_state.get("draft_card"):
            st.divider()
            st.subheader("Проверьте и отредактируйте карточку")
            st.caption("Баллы пересчитываются при каждом изменении. Публикация требует отдельного подтверждения.")
            _show_ai_result(st.session_state.get("card_result", {"mode": "demo", "reason": "demo_requested"}))
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

            st.session_state.draft_card = dict(candidate)
            evidence = st.session_state.get("card_result", {}).get("evidence", {})
            if any(evidence.values()):
                with st.expander("Источники AI-полей до ручного редактирования"):
                    for field, entries in evidence.items():
                        if entries:
                            st.markdown(f"**{CARD_FIELDS[field]}**")
                            for entry in entries:
                                source_label = "Черновик" if entry["source"] == "draft" else "Ответ бизнеса"
                                st.write(f"{source_label}: {entry['quote']}")

            st.markdown("### Текущий рейтинг")
            current_rating = _rating_panel(candidate)
            st.metric("Изменение полноты карточки", f"{current_rating['score'] - baseline['score']:+d} баллов")
            if st.button("Подтвердить и опубликовать", type="primary", key="publish_task"):
                if not owner_id:
                    st.error("Укажите рабочее пространство бизнеса в сайдбаре.")
                elif not candidate.get("title", "").strip():
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
    form_id = f"{task_id}_{team['id']}"
    if st.session_state.pop(f"clear_apply_{form_id}", False):
        for field in ("idea", "plan", "url"):
            st.session_state[f"apply_{field}_{form_id}"] = ""
        st.session_state[f"apply_team_{form_id}"] = team["name"]
    notice = st.session_state.pop(f"apply_notice_{form_id}", None)
    if notice:
        st.success(notice)
    with st.expander("Откликнуться на задачу", expanded=False):
        with st.form(f"application_form_{form_id}"):
            team_key = f"apply_team_{form_id}"
            if team_key not in st.session_state:
                st.session_state[team_key] = team["name"]
            st.text_input("Название команды", key=team_key)
            st.text_area("Идея решения", key=f"apply_idea_{form_id}", height=100, max_chars=3000)
            st.text_area("План работы", key=f"apply_plan_{form_id}", height=100, max_chars=3000)
            st.text_input(
                "Ссылка на прототип (необязательно)",
                key=f"apply_url_{form_id}",
                placeholder="https://...",
            )
            submitted = st.form_submit_button("Отправить отклик", type="primary")
        if submitted:
            team_name = str(st.session_state.get(team_key, "")).strip()
            idea = str(st.session_state.get(f"apply_idea_{form_id}", "")).strip()
            plan = str(st.session_state.get(f"apply_plan_{form_id}", "")).strip()
            url = str(st.session_state.get(f"apply_url_{form_id}", "")).strip()
            if not team_name or not idea or not plan:
                st.error("Укажите название команды, идею и план работы.")
            elif not is_valid_prototype_url(url):
                st.error("Укажите полный адрес прототипа, например https://example.com/prototype.")
            else:
                application = Application(
                    task_id=task_id,
                    team_name=team_name,
                    idea=idea,
                    plan=plan,
                    prototype_url=url,
                    team_id=team["id"],
                ).to_dict()
                st.session_state.applications.append(application)
                st.session_state[f"clear_apply_{form_id}"] = True
                st.session_state[f"apply_notice_{form_id}"] = "Отклик отправлен бизнесу."
                st.rerun()


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
            if prototype and is_valid_prototype_url(prototype):
                left.link_button("Открыть прототип", prototype)
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
        if "business_identity" not in st.session_state:
            st.session_state.business_identity = st.session_state.get("saved_business_identity", "Alem Retail")
        owner_id = st.sidebar.text_input("Рабочее пространство бизнеса", key="business_identity")
        st.session_state.saved_business_identity = owner_id
        if not owner_id.strip():
            st.sidebar.caption("Укажите имя компании, чтобы видеть её задачи.")
        st.sidebar.caption("Имя используется для списка «Мои задачи», это не аккаунт.")
        team = None
    else:
        teams = st.session_state.teams
        names = [item["name"] for item in teams]
        if "active_team" not in st.session_state:
            st.session_state.active_team = st.session_state.get("saved_active_team", names[0])
        team_name = st.sidebar.selectbox("Выберите команду", names, key="active_team")
        st.session_state.saved_active_team = team_name
        team = next(item for item in teams if item["name"] == team_name)
        st.sidebar.markdown("**Интересы**  \n" + ", ".join(team.get("interests", [])))
        st.sidebar.markdown("**Навыки**  \n" + ", ".join(team.get("skills", [])))
        st.sidebar.markdown("**Технологии**  \n" + ", ".join(team.get("technologies", [])))
        owner_id = ""
    st.sidebar.divider()
    _show_ai_mode()
    st.sidebar.caption("Для демо переключайте роли в одной вкладке. Данные хранятся в этой сессии браузера.")
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
