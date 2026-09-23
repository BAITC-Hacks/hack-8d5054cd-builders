"""Offline UI regressions for the complete business/team demo workflow."""

from pathlib import Path
from html import escape
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from src.ai import DEMO_ANSWERS, analyze_draft
from src.catalog import ALL_READINESS, ALL_TOPICS
from src.models import CARD_FIELDS


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"
OFFLINE_SETTINGS = {
    "demo": True,
    "provider": "auto",
    "timeout": 20.0,
    "openai_model": "offline-openai-model",
    "nvidia_model": "offline-nvidia-model",
    "openai_ready": False,
    "nvidia_ready": False,
}


class AppTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch("src.config.get_settings", side_effect=lambda: dict(OFFLINE_SETTINGS)))
        self.enterContext(patch("src.ai.get_settings", side_effect=lambda: dict(OFFLINE_SETTINGS)))
        self.env_reader = self.enterContext(patch(
            "src.config.reload_env", side_effect=AssertionError("Tests must not read the real .env")
        ))
        self.network = self.enterContext(patch(
            "src.ai._request_json", side_effect=AssertionError("Tests must not call an API")
        ))
        self.app = AppTest.from_file(str(APP_PATH), default_timeout=10).run()
        self.assert_no_app_errors()

    def tearDown(self):
        self.network.assert_not_called()
        self.env_reader.assert_not_called()

    def assert_no_app_errors(self):
        self.assertEqual([item.message for item in self.app.exception], [])

    def run_button(self, label):
        matches = [button for button in self.app.button if button.label == label]
        self.assertEqual(len(matches), 1, f"Expected a unique button: {label}")
        matches[0].click().run()
        self.assert_no_app_errors()

    def submit_form(self, form_id, label):
        self.app.button(key=f"FormSubmitter:{form_id}-{label}").click().run()
        self.assert_no_app_errors()

    def select_role(self, role):
        self.app.sidebar.radio(key="role").set_value(role).run()
        self.assert_no_app_errors()

    def select_business_page(self, page):
        self.app.sidebar.radio(key="business_page").set_value(page).run()
        self.assert_no_app_errors()

    def begin_demo_card(self):
        self.run_button("Попробовать на примере")
        self.run_button("Получить вопросы")
        self.run_button("Сформировать карточку")

    def visible_application_forms(self):
        return [button.key for button in self.app.button if str(button.key).startswith("FormSubmitter:application_form_")]

    def metric_value(self, label):
        matches = [metric for metric in self.app.metric if metric.label == label]
        self.assertEqual(len(matches), 1, f"Expected a unique metric: {label}")
        return matches[0].value

    def page_header(self):
        headers = [item.proto.body for item in self.app.get("html") if 'class="ui-page-header"' in item.proto.body]
        self.assertEqual(len(headers), 1, "Each page should have a single clear heading")
        return headers[0]

    def application_fields(self, form_id, *, idea="Построим воронку оформления заказа", plan="Проверим события, найдём узкие места и подготовим прототип", url=""):
        self.app.text_area(key=f"apply_idea_{form_id}").set_value(idea)
        self.app.text_area(key=f"apply_plan_{form_id}").set_value(plan)
        self.app.text_input(key=f"apply_url_{form_id}").set_value(url)

    def test_complete_demo_from_draft_to_manual_team_selection(self):
        initial_task_count = len(self.app.session_state.tasks)
        initial_application_count = len(self.app.session_state.applications)
        self.run_button("Попробовать на примере")
        self.run_button("Получить вопросы")
        self.assertEqual(self.metric_value("Рейтинг черновика"), "10 / 100")
        self.assertGreaterEqual(len(self.app.session_state.analysis["questions"]), 3)

        self.run_button("Сформировать карточку")
        self.assertEqual(self.metric_value("Изменение полноты карточки"), "+90 баллов")
        self.assertEqual(len(self.app.session_state.tasks), initial_task_count)
        self.run_button("Подтвердить и опубликовать")
        self.assertEqual(len(self.app.session_state.tasks), initial_task_count + 1)
        task = self.app.session_state.tasks[0]
        self.assertEqual((task["status"], task["rating"]), ("published", 100))
        self.assertEqual(task["owner_id"], "Alem Retail")

        self.select_role("Студенческая команда")
        form_id = f"{task['id']}_seed_team_1"
        self.application_fields(form_id, url="https://example.com/prototype")
        self.submit_form(f"application_form_{form_id}", "Отправить отклик")
        self.assertEqual(len(self.app.session_state.applications), initial_application_count + 1)
        application = self.app.session_state.applications[-1]
        self.assertEqual(application["task_id"], task["id"])
        self.assertEqual(application["status"], "pending")
        self.assertEqual(application["team_name"], "DataCraft")

        self.select_role("Бизнес")
        self.select_business_page("Мои задачи")
        self.app.button(key=f"choose_{application['id']}").click().run()
        self.assert_no_app_errors()
        selected = next(item for item in self.app.session_state.applications if item["id"] == application["id"])
        self.assertEqual(selected["status"], "selected")
        self.assertEqual(sum(item["status"] == "selected" for item in self.app.session_state.applications), 1)

    def test_empty_draft_explains_next_action_without_creating_questions(self):
        self.assertIn("Расскажите о задаче", self.page_header())
        self.run_button("Получить вопросы")
        self.assertEqual(self.app.session_state.builder_step, "draft")
        self.assertIsNone(self.app.session_state.analysis)
        self.assertTrue(any("описание задачи" in item.value for item in self.app.warning))
        self.assertEqual(self.app.text_area(key="draft_text").value, "")

    def test_empty_business_workspace_has_a_direct_path_to_creation(self):
        draft = "Нужно сократить время ожидания покупателей у стойки выдачи заказов."
        self.app.text_area(key="draft_text").set_value(draft).run()
        self.app.sidebar.text_input(key="business_identity").set_value("Новая компания").run()
        self.select_business_page("Мои задачи")
        self.assertIn("Ваши задачи", self.page_header())
        self.run_button("Создать первую задачу")
        self.assertEqual(self.app.sidebar.radio(key="business_page").value, "Новая задача")
        self.assertIn("Расскажите о задаче", self.page_header())
        self.assertEqual(self.app.text_area(key="draft_text").value, draft)

    def test_each_page_has_one_heading_and_catalog_keeps_experience_secondary(self):
        self.assertIn("Расскажите о задаче", self.page_header())
        self.assertEqual(len(self.app.main.title), 0)
        self.select_business_page("Мои задачи")
        self.assertIn("Ваши задачи", self.page_header())
        self.select_role("Студенческая команда")
        self.assertIn("Найдите задачу", self.page_header())
        self.assertFalse(any(item.label == "Подтверждённые XP" for item in self.app.metric))
        sidebar_html = "\n".join(item.proto.body for item in self.app.sidebar.get("html"))
        self.assertIn("0 баллов опыта", sidebar_html)
        for page in ("Мои отклики", "Мои проекты"):
            self.app.sidebar.radio(key="team_page").set_value(page).run()
            self.assert_no_app_errors()
            self.assertIn(page, self.page_header())
        dashboard = [item for item in self.app.expander if item.label == "Опыт и достижения команды"]
        self.assertEqual(len(dashboard), 1)
        self.assertFalse(dashboard[0].proto.expanded)
        self.assertEqual(self.metric_value("Подтверждённые XP"), "0")

    def test_all_review_fields_stay_editable_before_human_confirmation(self):
        initial_count = len(self.app.session_state.tasks)
        self.begin_demo_card()
        self.assertIn("Проверьте карточку", self.page_header())
        for field in CARD_FIELDS:
            widget = self.app.text_input(key=f"editor_{field}") if field == "title" else self.app.text_area(key=f"editor_{field}")
            self.assertFalse(widget.disabled, f"The business must be able to edit {field}")
            self.assertEqual(widget.value, DEMO_ANSWERS[field])
        self.assertFalse(self.app.button(key="publish_task").disabled)
        self.assertEqual(len(self.app.session_state.tasks), initial_count)

    def test_publication_receipt_escapes_business_and_task_names(self):
        company = '<b>Компания & партнёры</b>'
        title = '<img src=x onerror="alert(1)"> Задача'
        self.app.sidebar.text_input(key="business_identity").set_value(company).run()
        self.begin_demo_card()
        self.app.text_input(key="editor_title").set_value(title).run()
        self.run_button("Подтвердить и опубликовать")
        receipts = [item.proto.body for item in self.app.get("html") if '<section class="ui-summary ' in item.proto.body]
        self.assertEqual(len(receipts), 1)
        self.assertIn(escape(title, quote=True), receipts[0])
        self.assertIn(escape(company, quote=True), receipts[0])
        self.assertNotIn(title, receipts[0])
        self.assertEqual(self.app.session_state.tasks[0]["title"], title)

    def test_switching_teams_uses_clean_form_and_correct_identity(self):
        self.select_role("Студенческая команда")
        first_form = "seed_task_1_seed_team_1"
        self.application_fields(first_form, idea="Черновик только DataCraft", plan="План только DataCraft")
        self.app.run()
        self.assert_no_app_errors()
        self.app.sidebar.selectbox(key="active_team").set_value("Steppe AI").run()
        self.assert_no_app_errors()

        second_form = "seed_task_1_seed_team_3"
        self.assertEqual(self.app.text_input(key=f"apply_team_{second_form}").value, "Steppe AI")
        for field in ("idea", "plan"):
            self.assertEqual(self.app.text_area(key=f"apply_{field}_{second_form}").value, "")
        self.assertEqual(self.app.text_input(key=f"apply_url_{second_form}").value, "")

        self.application_fields(second_form, idea="Идея Steppe AI", plan="План Steppe AI")
        self.submit_form(f"application_form_{second_form}", "Отправить отклик")
        application = self.app.session_state.applications[-1]
        self.assertEqual((application["team_name"], application["team_id"]), ("Steppe AI", "seed_team_3"))
        self.assertEqual(application["idea"], "Идея Steppe AI")
        self.assertEqual(self.app.text_area(key=f"apply_idea_{second_form}").value, "")
        self.assertEqual(self.app.text_area(key=f"apply_plan_{second_form}").value, "")
        self.assertEqual(self.app.text_input(key=f"apply_team_{second_form}").value, "Steppe AI")

    def test_business_identity_survives_role_switches(self):
        self.app.sidebar.text_input(key="business_identity").set_value("Тестовая компания").run()
        self.assert_no_app_errors()
        self.select_role("Студенческая команда")
        self.select_role("Бизнес")
        self.assertEqual(self.app.sidebar.text_input(key="business_identity").value, "Тестовая компания")
        self.assertEqual(self.app.session_state.saved_business_identity, "Тестовая компания")

    def test_confirmed_edit_updates_stored_rating(self):
        self.select_business_page("Мои задачи")
        task = next(item for item in self.app.session_state.tasks if item["id"] == "seed_task_2")
        self.assertEqual(task["rating"], 80)
        self.app.text_area(key="edit_seed_task_2_data").set_value("История продаж и остатков товаров в CSV за два года.")
        self.assertEqual(task["data"], "")
        self.assertEqual(task["rating"], 80)
        self.submit_form("edit_task_seed_task_2", "Сохранить изменения и пересчитать рейтинг")
        updated = next(item for item in self.app.session_state.tasks if item["id"] == "seed_task_2")
        self.assertEqual(updated["rating"], 100)
        self.assertEqual(updated["data"], "История продаж и остатков товаров в CSV за два года.")
        self.assertTrue(any("100 / 100" in notice.value for notice in self.app.success))

    def test_invalid_prototype_urls_do_not_create_applications(self):
        self.select_role("Студенческая команда")
        form_id = "seed_task_1_seed_team_1"
        initial_count = len(self.app.session_state.applications)
        for url in ("https://", "http:/", "https:broken", "javascript:alert(1)"):
            with self.subTest(url=url):
                self.application_fields(form_id, url=url)
                self.submit_form(f"application_form_{form_id}", "Отправить отклик")
                self.assertEqual(len(self.app.session_state.applications), initial_count)
                self.assertTrue(any("полный адрес" in error.value for error in self.app.error))

    def test_labelled_draft_is_scored_from_all_locally_extracted_fields(self):
        draft = "\n".join(f"{label}: {DEMO_ANSWERS[field]}" for field, label in CARD_FIELDS.items())
        self.app.text_area(key="draft_text").set_value(draft)
        self.run_button("Получить вопросы")
        self.assertEqual(self.app.session_state.analysis["mode"], "demo")
        self.assertEqual(self.metric_value("Рейтинг черновика"), "100 / 100")
        for field, value in DEMO_ANSWERS.items():
            self.assertEqual(self.app.session_state.analysis["card"][field], value)
        self.assertGreaterEqual(len(self.app.session_state.analysis["questions"]), 3)

    def test_draft_and_saved_answers_survive_role_and_page_switches(self):
        draft = "Нужно сократить время обработки обращений покупателей в нашем магазине."
        self.app.text_area(key="draft_text").set_value(draft).run()
        self.assert_no_app_errors()
        self.select_role("Студенческая команда")
        self.select_role("Бизнес")
        self.assertEqual(self.app.text_area(key="draft_text").value, draft)
        self.assertEqual(self.app.session_state.saved_draft_text, draft)

        self.run_button("Получить вопросы")
        question = self.app.session_state.analysis["questions"][0]
        answer_key = f"answer_0_{question['field']}"
        answer = "Подтверждённый ответ бизнеса для продолжения работы после переключения роли."
        self.app.text_area(key=answer_key).set_value(answer)
        self.run_button("Сохранить ответы")
        self.select_role("Студенческая команда")
        self.select_role("Бизнес")
        self.assertEqual(self.app.session_state.builder_step, "clarify")
        self.assertEqual(self.app.text_area(key=answer_key).value, answer)
        self.select_business_page("Мои задачи")
        self.select_business_page("Новая задача")
        self.assertEqual(self.app.text_area(key=answer_key).value, answer)

    def test_manual_card_edits_and_topic_survive_role_switch(self):
        self.begin_demo_card()
        context = "Ручная правка: покупатели магазина не могут найти нужный способ оплаты."
        title = "Удобная оплата заказа"
        self.app.text_area(key="editor_context").set_value(context).run()
        self.app.text_input(key="editor_title").set_value(title).run()
        self.app.selectbox(key="editor_topic").set_value("Продукты и сервисы").run()
        self.assert_no_app_errors()
        self.select_role("Студенческая команда")
        self.select_role("Бизнес")
        self.assertEqual(self.app.session_state.builder_step, "review")
        self.assertEqual(self.app.text_area(key="editor_context").value, context)
        self.assertEqual(self.app.text_input(key="editor_title").value, title)
        self.assertEqual(self.app.selectbox(key="editor_topic").value, "Продукты и сервисы")
        self.assertEqual(self.app.session_state.draft_card["context"], context)

    def test_latest_editor_values_are_saved_during_simultaneous_role_switch(self):
        self.begin_demo_card()
        latest_need = "Нужно упростить выбор доставки, чтобы покупатели завершали оформление заказа."
        self.app.text_area(key="editor_need").set_value(latest_need)
        self.app.selectbox(key="editor_topic").set_value("Продукты и сервисы")
        self.select_role("Студенческая команда")
        self.select_role("Бизнес")
        self.assertEqual(self.app.session_state.builder_step, "review")
        self.assertEqual(self.app.text_area(key="editor_need").value, latest_need)
        self.assertEqual(self.app.session_state.draft_card["need"], latest_need)
        self.assertEqual(self.app.selectbox(key="editor_topic").value, "Продукты и сервисы")
        self.assertEqual(self.app.session_state.saved_editor_topic, "Продукты и сервисы")

    def test_team_project_page_survives_role_switch(self):
        self.select_role("Студенческая команда")
        self.app.sidebar.radio(key="team_page").set_value("Мои проекты").run()
        self.assert_no_app_errors()
        self.select_role("Бизнес")
        self.select_role("Студенческая команда")
        self.assertEqual(self.app.sidebar.radio(key="team_page").value, "Мои проекты")
        self.assertEqual(self.app.session_state.saved_team_page, "Мои проекты")
        self.assertIn("Мои проекты", self.page_header())

    def test_published_receipt_prevents_duplicate_publication_on_reruns(self):
        initial_count = len(self.app.session_state.tasks)
        self.begin_demo_card()
        self.run_button("Подтвердить и опубликовать")
        published_id = self.app.session_state.published_task_id
        self.assertEqual(self.app.session_state.builder_step, "published")
        self.assertFalse(any(button.label == "Подтвердить и опубликовать" for button in self.app.button))
        for _ in range(2):
            self.app.run()
            self.assert_no_app_errors()
        self.select_role("Студенческая команда")
        self.select_role("Бизнес")
        self.assertEqual(self.app.session_state.builder_step, "published")
        self.assertEqual(self.app.session_state.published_task_id, published_id)
        self.run_button("К моим задачам и откликам")
        self.assertEqual(self.app.sidebar.radio(key="business_page").value, "Мои задачи")
        self.select_business_page("Новая задача")
        self.assertFalse(any(button.label == "Подтвердить и опубликовать" for button in self.app.button))
        self.assertEqual(len(self.app.session_state.tasks), initial_count + 1)
        self.assertEqual(sum(item["id"] == published_id for item in self.app.session_state.tasks), 1)
        self.run_button("Создать другую задачу")
        self.assertEqual(self.app.session_state.builder_step, "draft")
        self.assertEqual(self.app.text_area(key="draft_text").value, "")
        self.assertEqual(len(self.app.session_state.tasks), initial_count + 1)

    def test_reanalyzing_unchanged_draft_preserves_answers_and_manual_card(self):
        with patch("src.ai.analyze_draft", wraps=analyze_draft) as analyzer:
            self.run_button("Попробовать на примере")
            self.run_button("Получить вопросы")
            question = self.app.session_state.analysis["questions"][0]
            answer_key = f"answer_0_{question['field']}"
            saved_answer = "Уточнение бизнеса, которое необходимо сохранить при повторном анализе."
            self.app.text_area(key=answer_key).set_value(saved_answer)
            self.run_button("Сформировать карточку")
            manual_value = "Результат вручную уточнён: интерактивный прототип нового оформления заказа."
            self.app.text_area(key="editor_expected_result").set_value(manual_value).run()
            self.assert_no_app_errors()
            self.run_button("Вернуться к вопросам")
            self.assertEqual(self.app.text_area(key=answer_key).value, saved_answer)
            self.run_button("Изменить черновик")
            self.run_button("Получить вопросы")
            self.assertEqual(analyzer.call_count, 1)
        self.assertEqual(self.app.session_state.builder_step, "review")
        self.assertEqual(self.app.text_area(key="editor_expected_result").value, manual_value)
        self.assertEqual(self.app.session_state.builder_answers[answer_key], saved_answer)

    def test_catalog_filters_reset_and_zero_rating_does_not_block_application(self):
        self.app.session_state.tasks.append({
            "id": "low_score_task", "title": "Тестовая образовательная задача",
            "status": "published", "owner_id": "Другая компания", "topic": "Образование",
            "created_at": "2026-09-23T10:00:00+00:00", "rating": 0,
        })
        self.select_role("Студенческая команда")
        all_forms = self.visible_application_forms()
        low_form_id = "low_score_task_seed_team_1"
        low_button_key = f"FormSubmitter:application_form_{low_form_id}-Отправить отклик"
        self.assertEqual(len(all_forms), len(self.app.session_state.tasks))
        self.assertIn(low_button_key, all_forms)
        self.app.selectbox(key="catalog_topic").set_value("Образование").run()
        self.app.selectbox(key="catalog_readiness").set_value("Черновик").run()
        self.assert_no_app_errors()
        self.assertEqual(self.visible_application_forms(), [low_button_key])
        self.assertFalse(self.app.button(key=low_button_key).disabled)
        self.assertTrue(any("Требует уточнения" in caption.value for caption in self.app.caption))
        self.assertTrue(any(f"№{len(all_forms)} из {len(all_forms)}" in caption.value for caption in self.app.caption))
        initial_application_count = len(self.app.session_state.applications)
        self.application_fields(low_form_id, idea="Сначала уточним проблему с бизнесом", plan="Проведём интервью и согласуем ожидаемый результат")
        self.submit_form(f"application_form_{low_form_id}", "Отправить отклик")
        self.assertEqual(len(self.app.session_state.applications), initial_application_count + 1)
        self.assertEqual(self.app.session_state.applications[-1]["task_id"], "low_score_task")
        self.run_button("Сбросить фильтры")
        self.assertEqual(self.app.selectbox(key="catalog_topic").value, ALL_TOPICS)
        self.assertEqual(self.app.selectbox(key="catalog_readiness").value, ALL_READINESS)
        self.assertEqual(self.visible_application_forms(), all_forms)


if __name__ == "__main__":
    unittest.main()
