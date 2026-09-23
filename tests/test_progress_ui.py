"""Offline Streamlit flows for human-confirmed project milestones."""

import unittest

from streamlit.testing.v1 import AppTest


FIXTURE = '''
import streamlit as st
from src.progress_ui import (
    render_team_dashboard, render_team_projects,
    render_team_applications, render_business_progress,
)
if "tasks" not in st.session_state:
    st.session_state.tasks = [{
        "id": "task_a", "owner_id": "Бизнес А", "status": "published",
        "title": "Проверяемое решение", "success_criteria": "Пройти пять сценариев прототипа.",
    }]
    st.session_state.teams = [{"id": "team_a", "name": "Команда А"}, {"id": "team_b", "name": "Команда Б"}]
    st.session_state.applications = [
        {"id": "app_a", "task_id": "task_a", "team_id": "team_a", "team_name": "Команда А", "status": "selected", "idea": "Первый план", "plan": "Проверка"},
        {"id": "app_b", "task_id": "task_a", "team_id": "team_a", "team_name": "Команда А", "status": "selected", "idea": "Второй план", "plan": "Повторное предложение"},
        {"id": "app_c", "task_id": "task_a", "team_id": "team_b", "team_name": "Команда Б", "status": "pending", "idea": "Другой план", "plan": "Анализ"},
    ]
    st.session_state.submissions = []
role = st.sidebar.radio("Тестовая роль", ["Команда", "Бизнес"], key="test_role")
if role == "Команда":
    team_id = st.sidebar.selectbox("Тестовая команда", ["team_a", "team_b"], key="test_team")
    team = next(team for team in st.session_state.teams if team["id"] == team_id)
    render_team_dashboard(team)
    render_team_projects(team)
    render_team_applications(team)
else:
    owner = st.sidebar.text_input("Тестовый бизнес", value="Бизнес А", key="test_owner")
    render_business_progress(st.session_state.tasks[0], owner)
'''


class ProgressUITests(unittest.TestCase):
    def setUp(self):
        self.app = AppTest.from_string(FIXTURE, default_timeout=10).run()
        self.assert_clean()

    def assert_clean(self):
        self.assertEqual([error.message for error in self.app.exception], [])

    def set_role(self, role):
        self.app.sidebar.radio(key="test_role").set_value(role).run()
        self.assert_clean()

    def submit_stage(self, stage_id, evidence="Подготовлен результат и выполнена проверка по пяти согласованным сценариям.", url="https://example.com/result"):
        form = f"stage_task_a_team_a_{stage_id}"
        self.app.text_area(key=f"{form}_evidence").set_value(evidence)
        self.app.text_input(key=f"{form}_url").set_value(url)
        self.app.button(key=f"FormSubmitter:{form}-Отправить этап на проверку").click().run()
        self.assert_clean()

    def review(self, stage_id, *, approve=True, feedback=""):
        row = next(row for row in self.app.session_state.submissions if row["stage_id"] == stage_id)
        form = f"review_{row['id']}"
        self.app.text_area(key=f"{form}_feedback").set_value(feedback)
        points = {"plan": 20, "prototype": 40, "result": 60}[stage_id]
        label = f"Подтвердить этап · +{points} XP" if approve else "Вернуть на доработку"
        self.app.button(key=f"FormSubmitter:{form}-{label}").click().run()
        self.assert_clean()

    def xp(self):
        return next(metric.value for metric in self.app.metric if metric.label == "Подтверждённые XP")

    def test_full_route_awards_only_after_business_confirmation(self):
        self.assertEqual(self.xp(), "0")
        total = 0
        for stage_id, points in (("plan", 20), ("prototype", 40), ("result", 60)):
            self.submit_stage(stage_id)
            self.assertEqual(self.xp(), str(total))
            row = next(row for row in self.app.session_state.submissions if row["stage_id"] == stage_id)
            self.assertEqual(row["status"], "pending")
            self.set_role("Бизнес")
            self.review(stage_id)
            self.app.run()
            self.assert_clean()
            self.set_role("Команда")
            total += points
            self.assertEqual(self.xp(), str(total))
        self.assertEqual(len(self.app.session_state.submissions), 3)
        self.assertTrue(any("Все три этапа подтверждены" in item.value for item in self.app.success))
        self.assertFalse(any(button.label == "Отправить этап на проверку" for button in self.app.button))

    def test_duplicate_selected_proposals_share_single_project_route(self):
        self.assertEqual(sum(button.label == "Отправить этап на проверку" for button in self.app.button), 1)
        self.submit_stage("plan")
        self.assertEqual(len(self.app.session_state.submissions), 1)
        self.set_role("Бизнес")
        self.assertEqual(sum(button.label == "Подтвердить этап · +20 XP" for button in self.app.button), 1)

    def test_revision_requires_feedback_and_keeps_prior_attempt(self):
        self.submit_stage("plan", evidence="Первоначальный план с описанными границами и проверкой результата.")
        self.set_role("Бизнес")
        self.review("plan", approve=False)
        self.assertTrue(self.app.error)
        self.assertEqual(self.app.session_state.submissions[0]["status"], "pending")
        self.review("plan", approve=False, feedback="Добавьте конкретные критерии проверки прототипа.")
        self.set_role("Команда")
        self.assertEqual(self.xp(), "0")
        self.assertTrue(any("вернул этап на доработку" in item.value for item in self.app.warning))
        self.submit_stage("plan", evidence="Обновлённый план: указаны пять конкретных критериев проверки и порядок приёмки.")
        row = self.app.session_state.submissions[0]
        self.assertEqual(row["attempt"], 2)
        self.assertEqual(len(row["history"]), 1)
        self.assertEqual(row["history"][0]["feedback"], "Добавьте конкретные критерии проверки прототипа.")
        self.set_role("Бизнес")
        self.review("plan", feedback="Теперь план согласован.")
        self.set_role("Команда")
        self.assertEqual(self.xp(), "20")

    def test_invalid_stage_does_not_create_submission(self):
        self.submit_stage("plan", url="javascript:alert(1)")
        self.assertEqual(self.app.session_state.submissions, [])
        self.assertTrue(self.app.error)
        self.submit_stage("plan", evidence="Мало", url="")
        self.assertEqual(self.app.session_state.submissions, [])

    def test_pending_team_has_no_stage_controls_or_another_teams_xp(self):
        self.submit_stage("plan")
        self.set_role("Бизнес")
        self.review("plan")
        self.set_role("Команда")
        self.app.sidebar.selectbox(key="test_team").set_value("team_b").run()
        self.assert_clean()
        self.assertEqual(self.xp(), "0")
        self.assertFalse(any(button.label == "Отправить этап на проверку" for button in self.app.button))
        self.assertTrue(any("Здесь появятся задачи" in item.value for item in self.app.info))

    def test_other_business_has_no_review_controls(self):
        self.submit_stage("plan")
        self.set_role("Бизнес")
        self.app.sidebar.text_input(key="test_owner").set_value("Бизнес Б").run()
        self.assert_clean()
        self.assertFalse(any("Подтвердить этап" in button.label for button in self.app.button))


if __name__ == "__main__":
    unittest.main()
