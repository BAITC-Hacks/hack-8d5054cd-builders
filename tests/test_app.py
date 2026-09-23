"""Offline UI regressions for the complete business/team demo workflow."""

from pathlib import Path
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from src.ai import DEMO_ANSWERS
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

    def metric_value(self, label):
        matches = [metric for metric in self.app.metric if metric.label == label]
        self.assertEqual(len(matches), 1, f"Expected a unique metric: {label}")
        return matches[0].value

    def application_fields(self, form_id, *, idea="Построим воронку оформления заказа", plan="Проверим события, найдём узкие места и подготовим прототип", url=""):
        self.app.text_area(key=f"apply_idea_{form_id}").set_value(idea)
        self.app.text_area(key=f"apply_plan_{form_id}").set_value(plan)
        self.app.text_input(key=f"apply_url_{form_id}").set_value(url)

    def test_complete_demo_from_draft_to_manual_team_selection(self):
        initial_task_count = len(self.app.session_state.tasks)
        initial_application_count = len(self.app.session_state.applications)
        self.run_button("Вставить пример для демо")
        self.run_button("Проанализировать")
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
        self.app.button(key=f"choose_{application['id']}").click().run()
        self.assert_no_app_errors()
        selected = next(item for item in self.app.session_state.applications if item["id"] == application["id"])
        self.assertEqual(selected["status"], "selected")
        self.assertEqual(sum(item["status"] == "selected" for item in self.app.session_state.applications), 1)

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
        self.run_button("Проанализировать")
        self.assertEqual(self.app.session_state.analysis["mode"], "demo")
        self.assertEqual(self.metric_value("Рейтинг черновика"), "100 / 100")
        for field, value in DEMO_ANSWERS.items():
            self.assertEqual(self.app.session_state.analysis["card"][field], value)
        self.assertGreaterEqual(len(self.app.session_state.analysis["questions"]), 3)


if __name__ == "__main__":
    unittest.main()
