from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import streamlit as st

from src.ai import DEMO_ANSWERS, DEMO_DRAFT, ERROR_LABELS, PROVIDER_LABELS, analyze_draft, build_card, check_connection
from src.config import get_settings
from src.catalog import ALL_READINESS, ALL_TOPICS, READINESS_LEVELS, TOPICS, catalog_position, next_readiness_target, normalize_topic, published_catalog
from src.models import CARD_FIELDS, Application, TaskCard, is_valid_prototype_url, make_id, utc_now
from src.rating import calculate_rating
from src.progress_ui import render_business_progress, render_team_applications, render_team_dashboard, render_team_projects


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
        _migrate_state()
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
    _migrate_state()


def _migrate_state() -> None:
    st.session_state.setdefault("submissions", [])
    st.session_state.setdefault("saved_draft_text", st.session_state.get("draft_text", ""))
    if "builder_step" not in st.session_state:
        st.session_state.builder_step = "review" if st.session_state.get("draft_card") else "clarify" if st.session_state.get("analysis") else "draft"
    names = {team["name"]: team["id"] for team in st.session_state.teams}
    for application in st.session_state.applications:
        if not application.get("team_id") and application.get("team_name") in names:
            application["team_id"] = names[application["team_name"]]
    for task in st.session_state.tasks:
        task["topic"] = normalize_topic(task.get("topic"))
        if task.get("status") == "published":
            task.setdefault("confirmed_at", task.get("created_at", ""))


def _show_ai_mode() -> None:
    settings = get_settings()
    with st.sidebar.expander("AI и подключение", expanded=False):
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
    st.session_state.saved_draft_text = ""
    st.session_state.builder_step = "draft"
    st.session_state.pop("published_task_id", None)
    st.session_state.pop("saved_editor_topic", None)
    st.session_state.use_demo_answers = False
    st.session_state.analysis = None
    st.session_state.analysis_draft = None
    st.session_state.draft_card = None
    st.session_state.card_source_mode = ""
    st.session_state.pop("card_result", None)
    st.session_state.pop("builder_answers", None)


def _rating_panel(card: dict[str, Any], *, compact: bool = False, preview: bool = False) -> dict[str, Any]:
    result = calculate_rating(card)
    left, middle, right = st.columns([1, 2, 3])
    left.metric("Предпросмотр рейтинга" if preview else "Подтверждённый рейтинг", f"{result['score']} / 100")
    middle.metric("Уровень готовности", result["level"])
    right.progress(result["score"] / 100)
    target = next_readiness_target(result["score"])
    if target and target["points_needed"]:
        st.caption(f"Следующая цель: {target['label']} · ещё {target['points_needed']} баллов.")
    if preview:
        st.caption("Это предварительный расчёт. Баллы и место в каталоге фиксируются после вашего подтверждения.")

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
        if application.get("id") == application_id and application.get("status") == "pending":
            application["status"] = status
            application["decided_at"] = utc_now()
            return


def _load_demo() -> None:
    _reset_builder()
    st.session_state.draft_text = DEMO_DRAFT
    st.session_state.saved_draft_text = DEMO_DRAFT
    st.session_state.use_demo_answers = True


def _open_my_tasks() -> None:
    st.session_state.business_page = "Мои задачи"


def _builder_go(step: str) -> None:
    st.session_state.builder_step = step


def _remember_draft() -> None:
    st.session_state.saved_draft_text = st.session_state.get("draft_text", "")


def _remember_editor(field: str) -> None:
    card = dict(st.session_state.get("draft_card") or {})
    card[field] = st.session_state.get(f"editor_{field}", "")
    st.session_state.draft_card = card


def _remember_topic() -> None:
    st.session_state.saved_editor_topic = st.session_state.get("editor_topic", "Другое")


def _save_answers(questions: list[dict[str, Any]]) -> dict[str, str]:
    answers_by_field: dict[str, list[str]] = {}
    for index, question in enumerate(questions):
        key = f"answer_{index}_{question['field']}"
        answer = str(st.session_state.get(key, "")).strip()
        st.session_state.setdefault("builder_answers", {})[key] = answer
        if answer:
            answers_by_field.setdefault(question["field"], []).append(answer)
    return {key: "\n".join(values) for key, values in answers_by_field.items()}


def render_new_task(owner_id: str) -> None:
    st.header("Конструктор задачи")
    st.write("Превратите описание проблемы в понятное предложение для студенческой команды.")
    step = st.session_state.builder_step
    steps = [("draft", "Черновик"), ("clarify", "Уточнение"), ("review", "Карточка и рейтинг"), ("published", "Публикация")]
    active = next((i for i, item in enumerate(steps) if item[0] == step), 0)
    st.caption(" → ".join(("✓ " if index < active else "") + label for index, (_, label) in enumerate(steps)))
    st.markdown(f"**Шаг {active + 1} из 4 · {steps[active][1]}**")
    st.progress((active + 1) / 4)

    if step == "published":
        task = next((t for t in st.session_state.tasks if t["id"] == st.session_state.get("published_task_id")), None)
        if task:
            rank, total = catalog_position(st.session_state.tasks, task["id"])
            st.success(f"«{task['title']}» опубликована от имени {task['owner_id']}.")
            st.metric("Подтверждённый рейтинг", f"{task['rating']} / 100")
            st.write(f"Место в общем каталоге: **{rank} из {total}**. Команды уже могут отправлять предложения.")
            st.info("Следующий шаг: сравните отклики в «Моих задачах» и выберите подходящие команды. После их отчётов здесь же можно подтвердить этапы работы.")
        left, right = st.columns(2)
        left.button("К моим задачам и откликам", type="primary", on_click=_open_my_tasks, use_container_width=True)
        right.button("Создать другую задачу", on_click=_reset_builder, use_container_width=True)
        return

    if step == "draft":
        sample, clear, _ = st.columns([1.4, 1, 2])
        sample.button("Вставить пример для демо", on_click=_load_demo, use_container_width=True)
        clear.button("Очистить", on_click=_reset_builder, use_container_width=True)
        if "draft_text" not in st.session_state:
            st.session_state.draft_text = st.session_state.saved_draft_text
        draft = st.text_area("Черновик задачи", key="draft_text", height=180, max_chars=8000,
                             on_change=_remember_draft,
                             placeholder="Что происходит сейчас? Что хотите изменить? Какие сведения уже есть?")
        _remember_draft()
        st.caption("Можно начать с нескольких предложений. На следующем шаге появятся вопросы по недостающим сведениям.")
        if st.button("Проанализировать", type="primary"):
            if not draft.strip():
                st.warning("Добавьте хотя бы краткое описание задачи.")
            elif st.session_state.get("analysis") and draft.strip() == st.session_state.get("analysis_draft"):
                st.session_state.builder_step = "review" if st.session_state.get("draft_card") else "clarify"
                st.rerun()
            else:
                with st.spinner("Находим сведения и уточняющие вопросы…"):
                    result = analyze_draft(draft.strip(), provider=st.session_state.ai_provider)
                st.session_state.analysis = result
                st.session_state.analysis_draft = draft.strip()
                st.session_state.draft_card = None
                st.session_state.pop("card_result", None)
                st.session_state.builder_answers = {}
                sample_answers = st.session_state.get("use_demo_answers") and draft.strip() == DEMO_DRAFT.strip()
                for index, question in enumerate(result["questions"]):
                    key = f"answer_{index}_{question['field']}"
                    st.session_state[key] = DEMO_ANSWERS.get(question["field"], "") if sample_answers else ""
                    st.session_state.builder_answers[key] = st.session_state[key]
                st.session_state.builder_step = "clarify"
                st.rerun()
        if st.session_state.get("analysis_draft") and draft.strip() != st.session_state.analysis_draft:
            st.warning("Черновик изменён. Новый анализ заменит прежние вопросы и собранную карточку.")
        return

    analysis = st.session_state.get("analysis")
    if not analysis:
        st.session_state.builder_step = "draft"
        st.rerun()
    current_draft = st.session_state.analysis_draft
    baseline_card = analysis.get("card") or {"context": current_draft}
    baseline = calculate_rating(baseline_card)

    if step == "clarify":
        st.subheader("Дополните то, чего пока не хватает")
        _show_ai_result(analysis)
        st.metric("Рейтинг черновика", f"{baseline['score']} / 100")
        st.caption("Предварительная полнота. В каталог попадут только подтверждённые сведения.")
        if analysis.get("baseline_quality") != "extracted":
            st.caption("В локальном режиме свободный текст учитывается как контекст, а строки «Данные: …» — как отдельные поля. Оценка может быть занижена.")
        with st.expander("Исходный черновик и найденные сведения"):
            st.write(current_draft)
            _render_task_contents(baseline_card)
        st.button("Изменить черновик", on_click=_builder_go, args=("draft",))
        if st.session_state.get("draft_card"):
            st.button("Вернуться к сохранённой карточке", on_click=_builder_go, args=("review",))
            st.caption("Повторное формирование карточки заменит её ручные правки. Можно сохранить ответы и вернуться к текущей карточке.")
        if st.session_state.get("use_demo_answers") and current_draft == DEMO_DRAFT.strip():
            st.caption("Демо-ответы заполнены примерными данными сценария. Вы можете изменить их.")
        with st.form("clarification_form"):
            st.subheader("Уточняющие вопросы")
            for index, question in enumerate(analysis["questions"]):
                field = question["field"]
                key = f"answer_{index}_{field}"
                if key not in st.session_state:
                    st.session_state[key] = st.session_state.get("builder_answers", {}).get(key, "")
                potential = next((row["potential_points"] for row in baseline["improvements"] if row["field"] == field), 0)
                if potential:
                    st.caption(f"{CARD_FIELDS[field]} · можно получить до +{potential} баллов после подтверждения")
                st.text_area(question["question"], key=key, height=90, max_chars=2000)
            st.caption("Если ответа пока нет, оставьте поле пустым. AI не должен придумывать данные за вас.")
            build_submitted = st.form_submit_button("Сформировать карточку", type="primary")
            save_answers = st.form_submit_button("Сохранить ответы")
        if save_answers or build_submitted:
            answers = _save_answers(analysis["questions"])
            if save_answers:
                st.success("Ответы сохранены. Можно вернуться к ним после переключения роли.")
            else:
                with st.spinner("Собираем карточку и проверяем источники фактов…"):
                    generated = build_card(current_draft, answers, provider=st.session_state.ai_provider, known_card=baseline_card)
                st.session_state.draft_card = generated["card"]
                st.session_state.card_result = generated
                for field in CARD_FIELDS:
                    st.session_state[f"editor_{field}"] = generated["card"].get(field, "")
                st.session_state.builder_step = "review"
                st.rerun()
        return

    st.subheader("Проверьте карточку перед публикацией")
    _show_ai_result(st.session_state.get("card_result", {"mode": "demo", "reason": "demo_requested"}))
    st.caption("Редактируйте любые поля. Название обязательно; неполную задачу тоже можно опубликовать.")
    st.button("Вернуться к вопросам", on_click=_builder_go, args=("clarify",))
    if "editor_topic" not in st.session_state:
        st.session_state.editor_topic = st.session_state.get("saved_editor_topic", "Другое")
    st.selectbox("Тема задачи", TOPICS, key="editor_topic", on_change=_remember_topic,
                 help="Тему выбирает бизнес. Она нужна для фильтра каталога и не влияет на баллы.")
    st.session_state.saved_editor_topic = st.session_state.editor_topic
    candidate: dict[str, str] = {}
    groups = [
        ("1. Суть задачи", ("title", "context", "need", "users")),
        ("2. Результат и условия", ("data", "constraints", "expected_result", "success_criteria")),
        ("3. Связь с бизнесом", ("contact", "collaboration_format")),
    ]
    for heading, fields in groups:
        with st.container(border=True):
            st.markdown(f"**{heading}**")
            columns = st.columns(2)
            for index, field in enumerate(fields):
                key = f"editor_{field}"
                if key not in st.session_state:
                    st.session_state[key] = st.session_state.draft_card.get(field, "")
                with columns[index % 2]:
                    if field == "title":
                        st.text_input(CARD_FIELDS[field], key=key, max_chars=200, on_change=_remember_editor, args=(field,))
                    else:
                        st.text_area(CARD_FIELDS[field], key=key, height=110, max_chars=8000, on_change=_remember_editor, args=(field,))
                candidate[field] = str(st.session_state.get(key, ""))
    st.session_state.draft_card = dict(candidate)
    evidence = st.session_state.get("card_result", {}).get("evidence", {})
    if any(evidence.values()):
        with st.expander("Источники AI-полей до ручного редактирования"):
            for field, entries in evidence.items():
                if entries:
                    st.markdown(f"**{CARD_FIELDS[field]}**")
                    for entry in entries:
                        st.write(f"{'Черновик' if entry['source'] == 'draft' else 'Ответ бизнеса'}: {entry['quote']}")
    st.markdown("### Паспорт готовности задачи")
    current_rating = _rating_panel(candidate, preview=True)
    st.metric("Изменение полноты карточки", f"{current_rating['score'] - baseline['score']:+d} баллов")
    st.info(f"Публикация от имени: **{owner_id or 'укажите компанию в сайдбаре'}**. Нажимая кнопку, вы подтверждаете сведения и открываете задачу всем командам.")
    if st.button("Подтвердить и опубликовать", type="primary", key="publish_task"):
        if not owner_id:
            st.error("Укажите рабочее пространство бизнеса в сайдбаре.")
        elif not candidate.get("title", "").strip():
            st.error("Перед публикацией укажите название задачи.")
        else:
            card = TaskCard.from_dict(candidate).to_dict()
            card.update(id=make_id("task"), owner_id=owner_id, status="published", created_at=utc_now(),
                        confirmed_at=utc_now(), rating=current_rating["score"], topic=st.session_state.editor_topic)
            st.session_state.tasks.insert(0, card)
            st.session_state.published_task_id = card["id"]
            st.session_state.builder_step = "published"
            st.session_state.draft_card = None
            st.rerun()


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
            st.text_input("Название команды", key=team_key, disabled=True)
            st.caption("Отклик относится к выбранному профилю команды. Сменить команду можно в сайдбаре.")
            st.text_area("Идея решения", key=f"apply_idea_{form_id}", height=100, max_chars=3000)
            st.text_area("План работы", key=f"apply_plan_{form_id}", height=100, max_chars=3000)
            st.text_input(
                "Ссылка на прототип (необязательно)",
                key=f"apply_url_{form_id}",
                placeholder="https://...",
            )
            submitted = st.form_submit_button("Отправить отклик", type="primary")
        if submitted:
            team_name = team["name"]
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
                st.session_state[f"apply_notice_{form_id}"] = "Отклик отправлен. Его статус доступен в разделе «Мои отклики». XP начисляется после принятия этапов работы."
                st.rerun()


def render_catalog(team: dict[str, Any]) -> None:
    st.header("Открытый каталог")
    st.write("Выберите задачу и предложите решение. Рейтинг показывает, насколько подробно бизнес подготовил условия работы.")
    all_tasks = published_catalog(st.session_state.tasks)
    if not all_tasks:
        st.info("Пока нет опубликованных задач.")
        return
    topic_col, level_col, reset_col = st.columns([2, 2, 1])
    topic = topic_col.selectbox("Тема", (ALL_TOPICS, *TOPICS), key="catalog_topic")
    readiness = level_col.selectbox("Готовность", (ALL_READINESS, *READINESS_LEVELS), key="catalog_readiness")
    reset_col.button("Сбросить фильтры", on_click=_reset_catalog_filters)
    tasks = published_catalog(st.session_state.tasks, topic, readiness)
    st.caption(f"Показано {len(tasks)} из {len(all_tasks)}. Сначала задачи с высоким рейтингом; при равенстве — опубликованные раньше. Любой команде доступен отклик при любом балле.")
    if not tasks:
        st.info("По этим фильтрам задач пока нет. Сбросьте фильтры, чтобы увидеть весь каталог.")
    positions = {task["id"]: index for index, task in enumerate(all_tasks, 1)}
    for task in tasks:
        rating = calculate_rating(task)
        with st.container(border=True):
            head, score_col = st.columns([4, 1])
            head.subheader(task.get("title") or "Задача без названия")
            head.caption(f"{task['topic']} · {task.get('owner_id') or 'Не указано'} · {_application_count(task['id'])} откликов")
            head.caption(f"№{positions[task['id']]} из {len(all_tasks)} в общем каталоге")
            score_col.metric("Рейтинг", f"{rating['score']} / 100")
            score_col.caption(("★ " if rating['score'] >= 90 else "") + rating["level"])
            st.progress(rating["score"] / 100)
            if rating["score"] < 40:
                st.caption("Требует уточнения. Вы можете откликнуться и предложить, с чего начать.")
            st.write(task.get("expected_result") or task.get("need") or "Ожидаемый результат предстоит уточнить с бизнесом.")
            with st.expander("Посмотреть карточку"):
                _render_task_contents(task)
                _rating_panel(task, compact=True)
            render_application(task, team)


def _reset_catalog_filters() -> None:
    st.session_state.catalog_topic = ALL_TOPICS
    st.session_state.catalog_readiness = ALL_READINESS


def _render_edit_form(task: dict[str, Any]) -> None:
    notice_key = f"edit_notice_{task['id']}"
    with st.expander("Редактировать опубликованную карточку"):
        with st.form(f"edit_task_{task['id']}"):
            topic_key = f"edit_topic_{task['id']}"
            if topic_key not in st.session_state:
                st.session_state[topic_key] = normalize_topic(task.get("topic"))
            st.selectbox("Тема задачи", TOPICS, key=topic_key)
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
                task["topic"] = st.session_state[topic_key]
                task["confirmed_at"] = utc_now()
                rank, total = catalog_position(st.session_state.tasks, task['id'])
                st.session_state[notice_key] = f"Изменения подтверждены. Новый рейтинг: {task['rating']} / 100. Место в общем каталоге: {rank} из {total}."
                st.rerun()
    if st.session_state.get(notice_key):
        st.success(st.session_state.pop(notice_key))


def _render_applications(task: dict[str, Any]) -> None:
    applications = [app for app in st.session_state.applications if app.get("task_id") == task["id"]]
    st.markdown(f"**Отклики ({len(applications)})**")
    if not applications:
        st.caption("Пока откликов нет.")
        return
    st.caption("Сравните идеи и планы. Можно выбрать одну, несколько или ни одной команды; выбор открывает команде этапы проекта.")
    if len(applications) > 1:
        with st.expander("Сравнить предложения", expanded=True):
            status_labels = {"pending": "На рассмотрении", "selected": "Выбрана", "rejected": "Отклонена"}
            st.dataframe([{"Команда": app["team_name"], "Идея": app.get("idea", ""),
                           "План": app.get("plan", ""), "Статус": status_labels.get(app.get("status"), "На рассмотрении")}
                          for app in applications], hide_index=True, use_container_width=True)
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
        st.info("У этого бизнеса пока нет опубликованных задач. Создайте карточку в разделе «Новая задача».")
        return
    ids = {task["id"] for task in tasks}
    stats = st.columns(3)
    stats[0].metric("Опубликовано задач", len(tasks))
    stats[1].metric("Откликов на рассмотрении", sum(app.get("task_id") in ids and app.get("status") == "pending" for app in st.session_state.applications))
    stats[2].metric("Этапов на проверке", sum(item.get("task_id") in ids and item.get("status") == "pending" for item in st.session_state.submissions))
    for task in tasks:
        rating = calculate_rating(task)
        with st.container(border=True):
            title_col, metric_col = st.columns([4, 1])
            title_col.subheader(task.get("title") or "Задача без названия")
            title_col.caption(f"{rating['level']} · { _application_count(task['id']) } откликов")
            rank, total = catalog_position(st.session_state.tasks, task["id"])
            title_col.caption(f"{task['topic']} · №{rank} из {total} в общем каталоге")
            metric_col.metric("Рейтинг", f"{rating['score']} / 100")
            st.progress(rating["score"] / 100)
            _render_edit_form(task)
            with st.expander("Как повысить готовность задачи"):
                _rating_panel(task, compact=True)
            _render_applications(task)
            render_business_progress(task, owner_id)


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
        if "business_page" not in st.session_state:
            st.session_state.business_page = st.session_state.get("saved_business_page", "Новая задача")
        st.sidebar.radio("Раздел", ["Новая задача", "Мои задачи"], key="business_page")
        st.session_state.saved_business_page = st.session_state.business_page
        team = None
    else:
        teams = st.session_state.teams
        names = [item["name"] for item in teams]
        if "active_team" not in st.session_state:
            st.session_state.active_team = st.session_state.get("saved_active_team", names[0])
        team_name = st.sidebar.selectbox("Выберите команду", names, key="active_team")
        st.session_state.saved_active_team = team_name
        team = next(item for item in teams if item["name"] == team_name)
        if "team_page" not in st.session_state:
            st.session_state.team_page = st.session_state.get("saved_team_page", "Каталог")
        st.sidebar.radio("Раздел команды", ["Каталог", "Мои отклики", "Мои проекты"], key="team_page")
        st.session_state.saved_team_page = st.session_state.team_page
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
    st.title("HackAlem · От задачи к результату")
    st.caption("Бизнес готовит понятную задачу. Команда предлагает решение и получает опыт за принятые этапы.")

    if role == "Бизнес":
        if st.session_state.business_page == "Новая задача":
            render_new_task(owner_id)
        else:
            render_my_tasks(owner_id)
    else:
        assert team is not None
        render_team_dashboard(team)
        if st.session_state.team_page == "Каталог":
            render_catalog(team)
        elif st.session_state.team_page == "Мои отклики":
            render_team_applications(team)
        else:
            render_team_projects(team)


if __name__ == "__main__":
    main()
