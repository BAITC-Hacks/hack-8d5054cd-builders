"""Complete eight-step scenario through the real app, without credentials or APIs."""

from pathlib import Path
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"
OFFLINE_SETTINGS = {
    "demo": True, "provider": "auto", "timeout": 20.0,
    "openai_model": "offline-openai", "nvidia_model": "offline-nvidia",
    "openai_ready": False, "nvidia_ready": False,
}
EVIDENCE = "Подготовлен результат, проверены пять согласованных сценариев, замечания записаны в отчёте."


class JourneyTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch("src.config.get_settings", side_effect=lambda: dict(OFFLINE_SETTINGS)))
        self.enterContext(patch("src.ai.get_settings", side_effect=lambda: dict(OFFLINE_SETTINGS)))
        self.env_reader = self.enterContext(patch("src.config.reload_env", side_effect=AssertionError("Do not read the real .env")))
        self.network = self.enterContext(patch("src.ai._request_json", side_effect=AssertionError("Do not call external APIs")))
        self.app = AppTest.from_file(str(APP_PATH), default_timeout=15).run()
        self.assert_clean()

    def tearDown(self):
        self.env_reader.assert_not_called()
        self.network.assert_not_called()

    def assert_clean(self):
        self.assertEqual([error.message for error in self.app.exception], [])

    def click(self, *, label=None, key=None):
        if key is not None:
            button = self.app.button(key=key)
        else:
            buttons = [button for button in self.app.button if button.label == label]
            self.assertEqual(len(buttons), 1, f"Button must be unique: {label}")
            button = buttons[0]
        button.click().run()
        self.assert_clean()

    def metric(self, label):
        matches = [metric.value for metric in self.app.metric if metric.label == label]
        self.assertEqual(len(matches), 1, f"Metric must be unique: {label}")
        return matches[0]

    def business(self):
        self.app.sidebar.radio(key="role").set_value("Бизнес").run()
        self.assert_clean()
        self.app.sidebar.radio(key="business_page").set_value("Мои задачи").run()
        self.assert_clean()

    def team(self, name="DataCraft", page="Мои проекты"):
        self.app.sidebar.radio(key="role").set_value("Студенческая команда").run()
        self.assert_clean()
        self.app.sidebar.selectbox(key="active_team").set_value(name).run()
        self.assert_clean()
        self.app.sidebar.radio(key="team_page").set_value(page).run()
        self.assert_clean()

    def propose(self, task_id, team_id):
        form = f"{task_id}_{team_id}"
        self.app.text_area(key=f"apply_idea_{form}").set_value("Покажем причины проблемы и подготовим проверяемое решение.")
        self.app.text_area(key=f"apply_plan_{form}").set_value("Согласуем план, проверим прототип, передадим результат бизнесу.")
        self.app.text_input(key=f"apply_timeline_{form}").set_value("Прототип за 2 недели, результат за 4 недели")
        self.app.text_input(key=f"apply_url_{form}").set_value("https://example.org/prototype")
        self.click(key=f"FormSubmitter:application_form_{form}-Отправить отклик")
        return dict(self.app.session_state.applications[-1])

    def submit_stage(self, task_id, team_id, stage_id):
        form = f"stage_{task_id}_{team_id}_{stage_id}"
        self.app.text_area(key=f"{form}_evidence").set_value(EVIDENCE)
        self.app.text_input(key=f"{form}_url").set_value("https://example.org/result")
        self.click(key=f"FormSubmitter:{form}-Отправить этап на проверку")
        return next(dict(row) for row in self.app.session_state.submissions if row["task_id"] == task_id and row["team_id"] == team_id and row["stage_id"] == stage_id)

    def approve(self, submission, xp):
        self.click(key=f"FormSubmitter:review_{submission['id']}-Подтвердить этап · +{xp} XP")

    def test_complete_eight_step_journey_and_all_three_accepted_stages(self):
        initial_tasks = len(self.app.session_state.tasks)
        self.click(label="Попробовать на примере")
        self.click(label="Получить вопросы")
        self.assertEqual(self.app.session_state.builder_step, "clarify")
        self.assertEqual(self.metric("Рейтинг черновика"), "10 / 100")
        self.assertGreaterEqual(len(self.app.session_state.analysis["questions"]), 3)
        self.click(label="Сформировать карточку")
        self.assertEqual(self.app.session_state.builder_step, "review")
        self.assertEqual(self.metric("Изменение полноты карточки"), "+90 баллов")
        self.assertEqual(len(self.app.session_state.tasks), initial_tasks)
        self.assertTrue(self.app.text_area(key="editor_success_criteria").value)
        self.click(key="publish_task")
        self.assertEqual(self.app.session_state.builder_step, "published")
        task = dict(self.app.session_state.tasks[0])
        self.assertEqual((task["status"], task["rating"], task["owner_id"]), ("published", 100, "Alem Retail"))
        self.assertTrue(task["confirmed_at"])
        receipt = [item.proto.body for item in self.app.get("html") if '<section class="ui-summary ' in item.proto.body]
        self.assertTrue(any("100 баллов" in item and task["title"] in item for item in receipt))

        self.team(page="Каталог")
        application = self.propose(task["id"], "seed_team_1")
        self.assertEqual(application["status"], "pending")
        self.app.sidebar.radio(key="team_page").set_value("Мои проекты").run()
        self.assert_clean()
        self.assertEqual(self.metric("Подтверждённые XP"), "0")
        self.assertFalse(any(button.label == "Отправить этап на проверку" for button in self.app.button))

        self.business()
        self.click(key=f"choose_{application['id']}")
        selected = next(row for row in self.app.session_state.applications if row["id"] == application["id"])
        self.assertEqual(selected["status"], "selected")
        self.assertEqual(self.app.session_state.submissions, [])
        self.team()
        self.assertEqual(self.metric("Подтверждённые XP"), "0")

        total = 0
        for stage_id, xp in (("plan", 20), ("prototype", 40), ("result", 60)):
            with self.subTest(stage=stage_id):
                submission = self.submit_stage(task["id"], "seed_team_1", stage_id)
                self.assertEqual(submission["status"], "pending")
                self.assertEqual(self.metric("Подтверждённые XP"), str(total))
                self.business()
                self.assertEqual(self.metric("Результаты на проверке"), "1")
                self.approve(submission, xp)
                self.assertEqual(self.metric("Результаты на проверке"), "0")
                self.team()
                total += xp
                self.assertEqual(self.metric("Подтверждённые XP"), str(total))
                self.assertTrue(any("Первый согласованный план" in item.value for item in self.app.markdown))

        self.assertEqual(total, 120)
        self.assertEqual(self.metric("Завершено проектов"), "1")
        self.assertEqual(self.metric("Уровень команды"), "Практик")
        self.assertTrue(all(row["status"] == "approved" for row in self.app.session_state.submissions))
        self.assertFalse(any(button.label == "Отправить этап на проверку" for button in self.app.button))
        self.app.run()
        self.assert_clean()
        self.assertEqual(self.metric("Подтверждённые XP"), "120")

    def test_existing_seed_proposal_becomes_project_only_after_manual_choice(self):
        self.assertTrue(all(app.get("team_id") for app in self.app.session_state.applications))
        self.team()
        self.assertFalse(any(button.label == "Отправить этап на проверку" for button in self.app.button))
        self.business()
        self.click(key="choose_seed_application_1")
        self.team()
        self.assertIsNotNone(self.app.text_area(key="stage_seed_task_1_seed_team_1_plan_evidence"))
        self.assertEqual(self.metric("Подтверждённые XP"), "0")
        self.assertEqual(self.app.session_state.submissions, [])
        self.team(name="FlowLab")
        self.assertFalse(any(button.label == "Отправить этап на проверку" for button in self.app.button))
        self.assertEqual(self.metric("Подтверждённые XP"), "0")

    def test_two_manually_selected_teams_keep_independent_progress(self):
        self.team(name="FlowLab", page="Каталог")
        second_application = self.propose("seed_task_1", "seed_team_2")
        self.business()
        self.click(key="choose_seed_application_1")
        self.click(key=f"choose_{second_application['id']}")
        selected = [row for row in self.app.session_state.applications if row["task_id"] == "seed_task_1" and row["status"] == "selected"]
        self.assertEqual({row["team_id"] for row in selected}, {"seed_team_1", "seed_team_2"})

        self.team()
        first = self.submit_stage("seed_task_1", "seed_team_1", "plan")
        self.team(name="FlowLab")
        second = self.submit_stage("seed_task_1", "seed_team_2", "plan")
        self.assertNotEqual(first["id"], second["id"])
        self.business()
        self.assertEqual(self.metric("Результаты на проверке"), "2")
        self.approve(first, 20)
        self.assertEqual(self.metric("Результаты на проверке"), "1")
        self.team()
        self.assertEqual(self.metric("Подтверждённые XP"), "20")
        self.assertIsNotNone(self.app.text_area(key="stage_seed_task_1_seed_team_1_prototype_evidence"))
        self.team(name="FlowLab")
        self.assertEqual(self.metric("Подтверждённые XP"), "0")
        self.assertTrue(any("на проверке у бизнеса" in item.value for item in self.app.info))
        self.assertFalse(any(button.label == "Отправить этап на проверку" for button in self.app.button))
        self.team(name="Steppe AI")
        self.assertFalse(any(button.label == "Отправить этап на проверку" for button in self.app.button))
        self.assertEqual(self.metric("Подтверждённые XP"), "0")


if __name__ == "__main__":
    unittest.main()
