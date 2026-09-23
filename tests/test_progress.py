"""Offline checks for approved progress, sequential stages and non-repeatable XP."""

from copy import deepcopy
import unittest

from src.progress import MILESTONES, project_stages, review_stage, submit_stage, team_summary


EVIDENCE = "Согласовали план и пять проверочных сценариев с представителем бизнеса."


class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.tasks = [{"id": "task_1", "owner_id": "business_1", "status": "published"}]
        self.apps = [
            {"id": "app_1", "task_id": "task_1", "team_id": "team_1", "status": "selected"},
            {"id": "app_2", "task_id": "task_1", "team_id": "team_2", "status": "pending"},
        ]

    def submit(self, submissions=None, stage="plan", team="team_1", evidence=EVIDENCE, url=""):
        return submit_stage(self.tasks, self.apps, submissions or [], "task_1", team, stage, evidence, url)

    def review(self, submissions, decision="approve", feedback="", owner="business_1", index=-1):
        return review_stage(self.tasks, self.apps, submissions, owner, submissions[index]["id"], decision, feedback)

    def finish(self, rows=None):
        rows = rows or []
        for stage in MILESTONES:
            rows = self.review(self.submit(rows, stage=stage["id"]))
        return rows

    def test_new_project_unlocks_plan_only(self):
        stages = project_stages([], "task_1", "team_1")
        self.assertEqual([stage["status"] for stage in stages], ["available", "locked", "locked"])
        self.assertEqual([stage["xp"] for stage in stages], [20, 40, 60])
        self.assertTrue(all(stage["submission"] is None for stage in stages))

    def test_selected_team_submits_without_earning_xp(self):
        rows = self.submit(url="https://example.org/plan")
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["status"], rows[0]["attempt"], rows[0]["awarded_xp"]), ("pending", 1, 0))
        self.assertEqual(team_summary(rows, "team_1")["xp"], 0)
        self.assertEqual(project_stages(rows, "task_1", "team_1")[1]["status"], "locked")

    def test_pending_rejected_missing_and_blank_teams_cannot_submit(self):
        for status in ("pending", "rejected"):
            self.apps[1]["status"] = status
            with self.subTest(status=status), self.assertRaises(ValueError):
                self.submit(team="team_2")
        for team in ("missing", ""):
            with self.subTest(team=team), self.assertRaises(ValueError):
                self.submit(team=team)

    def test_missing_or_unpublished_task_cannot_submit(self):
        for task_state in ([], [{"id": "task_1", "status": "draft", "owner_id": "business_1"}]):
            with self.subTest(task_state=task_state), self.assertRaises(ValueError):
                submit_stage(task_state, self.apps, [], "task_1", "team_1", "plan", EVIDENCE)

    def test_unknown_stage_rejected(self):
        with self.assertRaises(ValueError):
            self.submit(stage="bonus")

    def test_cannot_skip_stages_or_submit_before_approval(self):
        for rows in ([], self.submit()):
            for stage in ("prototype", "result"):
                with self.subTest(rows=rows, stage=stage), self.assertRaises(ValueError):
                    self.submit(rows, stage=stage)

    def test_accepting_plan_awards_twenty_and_unlocks_prototype(self):
        rows = self.review(self.submit(), feedback="План согласован.")
        self.assertEqual(rows[0]["status"], "approved")
        self.assertEqual(rows[0]["awarded_xp"], 20)
        self.assertEqual(rows[0]["reviewed_by"], "business_1")
        self.assertTrue(rows[0]["reviewed_at"])
        summary = team_summary(rows, "team_1")
        self.assertEqual((summary["xp"], summary["level_name"]), (20, "Исследователь"))
        self.assertEqual([stage["status"] for stage in project_stages(rows, "task_1", "team_1")], ["approved", "available", "locked"])

    def test_owner_only_review(self):
        rows = self.submit()
        for owner in ("business_2", ""):
            with self.subTest(owner=owner), self.assertRaises(ValueError):
                self.review(rows, owner=owner)

    def test_no_review_after_team_deselected_or_task_unpublished(self):
        rows = self.submit()
        self.apps[0]["status"] = "rejected"
        with self.assertRaises(ValueError):
            self.review(rows)
        self.apps[0]["status"] = "selected"
        self.tasks[0]["status"] = "draft"
        with self.assertRaises(ValueError):
            self.review(rows)

    def test_revision_requires_feedback_and_earns_no_xp(self):
        rows = self.submit()
        for feedback in ("", " ", "нет"):
            with self.subTest(feedback=feedback), self.assertRaises(ValueError):
                self.review(rows, decision="revise", feedback=feedback)
        revised = self.review(rows, decision="revise", feedback="Добавьте конкретные критерии приёмки.")
        self.assertEqual(revised[0]["status"], "revision")
        self.assertEqual(team_summary(revised, "team_1")["xp"], 0)

    def test_revision_resubmit_preserves_id_history_and_attempt(self):
        original = self.submit()
        revised = self.review(original, decision="revise", feedback="Добавьте критерии приёмки.")
        resubmitted = self.submit(revised, evidence="Добавлены критерии приёмки: все пять сценариев проходят проверку.")
        self.assertEqual(len(resubmitted), 1)
        self.assertEqual(resubmitted[0]["id"], original[0]["id"])
        self.assertEqual((resubmitted[0]["status"], resubmitted[0]["attempt"]), ("pending", 2))
        self.assertEqual(resubmitted[0]["feedback"], "")
        history = resubmitted[0]["history"]
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["evidence"], EVIDENCE)
        self.assertEqual(history[0]["feedback"], "Добавьте критерии приёмки.")
        self.assertNotIn("history", history[0])
        self.assertEqual(team_summary(self.review(resubmitted), "team_1")["xp"], 20)

    def test_pending_and_approved_cannot_be_resubmitted(self):
        pending = self.submit()
        for rows in (pending, self.review(pending)):
            with self.subTest(status=rows[0]["status"]), self.assertRaises(ValueError):
                self.submit(rows)

    def test_approved_and_revision_cannot_be_reviewed_again(self):
        pending = self.submit()
        for rows in (self.review(pending), self.review(pending, decision="revise", feedback="Добавьте критерии приёмки.")):
            with self.subTest(status=rows[0]["status"]), self.assertRaises(ValueError):
                self.review(rows)

    def test_duplicate_selected_applications_cannot_farm_xp(self):
        self.apps.append({**self.apps[0], "id": "app_duplicate"})
        rows = self.review(self.submit())
        with self.assertRaises(ValueError):
            self.submit(rows)
        self.assertEqual(team_summary(rows, "team_1")["xp"], 20)
        duplicate = deepcopy(rows[0])
        duplicate["id"] = "corrupt_duplicate"
        duplicate["awarded_xp"] = 9999
        self.assertEqual(team_summary(rows + [duplicate], "team_1")["xp"], 20)
        with self.assertRaises(ValueError):
            project_stages(rows + [duplicate], "task_1", "team_1")

    def test_full_project_earns_120_xp_and_three_badges(self):
        rows = self.finish()
        summary = team_summary(rows, "team_1")
        self.assertEqual(summary["xp"], 120)
        self.assertEqual(summary["approved_stages"], 3)
        self.assertEqual(summary["completed_projects"], 1)
        self.assertEqual(summary["level_name"], "Практик")
        self.assertEqual(len(summary["badges"]), 3)
        self.assertEqual([row["awarded_xp"] for row in rows], [20, 40, 60])

    def test_separate_teams_have_independent_progress(self):
        self.apps[1]["status"] = "selected"
        rows = self.finish()
        self.assertEqual(team_summary(rows, "team_2")["xp"], 0)
        rows = self.review(self.submit(rows, team="team_2"))
        self.assertEqual(team_summary(rows, "team_1")["xp"], 120)
        self.assertEqual(team_summary(rows, "team_2")["xp"], 20)

    def test_different_projects_earn_separate_xp(self):
        rows = self.finish()
        self.tasks.append({"id": "task_2", "owner_id": "business_1", "status": "published"})
        self.apps.append({"id": "app_other", "task_id": "task_2", "team_id": "team_1", "status": "selected"})
        rows = submit_stage(self.tasks, self.apps, rows, "task_2", "team_1", "plan", EVIDENCE)
        rows = self.review(rows)
        self.assertEqual(team_summary(rows, "team_1")["xp"], 140)
        self.assertEqual(team_summary(rows, "team_1")["completed_projects"], 1)

    def test_functions_do_not_mutate_inputs_or_expose_shared_records(self):
        inputs = (deepcopy(self.tasks), deepcopy(self.apps), [])
        rows = self.submit(inputs[2])
        self.assertEqual((self.tasks, self.apps, inputs[2]), inputs)
        before = deepcopy(rows)
        reviewed = self.review(rows)
        self.assertEqual(rows, before)
        self.assertIsNot(reviewed, rows)
        stages = project_stages(reviewed, "task_1", "team_1")
        stages[0]["submission"]["evidence"] = "Changed by UI"
        self.assertEqual(reviewed[0]["evidence"], EVIDENCE)

    def test_evidence_limits(self):
        for evidence in ("", "Short", "x" * 4001, None):
            with self.subTest(evidence=str(evidence)[:20]), self.assertRaises(ValueError):
                self.submit(evidence=evidence)

    def test_optional_links_validated(self):
        for url in ("", "https://example.org/demo", "http://localhost:8501"):
            with self.subTest(url=url):
                self.assertEqual(self.submit(url=url)[0]["url"], url)
        for url in ("javascript:alert(1)", "file:///secret", "https://", "https://a b.test", "https://user:pass@example.org", "https://example.org:99999"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                self.submit(url=url)

    def test_invalid_review_id_and_decision(self):
        rows = self.submit()
        with self.assertRaises(ValueError):
            review_stage(self.tasks, self.apps, rows, "business_1", "missing", "approve")
        with self.assertRaises(ValueError):
            self.review(rows, decision="auto_accept")

    def test_review_revalidates_stage_prerequisites(self):
        rows = self.submit()
        rows[0]["stage_id"] = "result"
        with self.assertRaises(ValueError):
            self.review(rows)

    def test_empty_summary_and_max_level(self):
        summary = team_summary([], "team_1")
        self.assertEqual((summary["xp"], summary["level"], summary["level_name"], summary["next_level_xp"]), (0, 1, "Старт", 20))
        self.assertEqual(summary["badges"], [])
        rows = [
            {"task_id": task, "team_id": "team_1", "stage_id": stage["id"], "status": "approved"}
            for task in ("a", "b", "c") for stage in MILESTONES
        ]
        summary = team_summary(rows, "team_1")
        self.assertEqual((summary["xp"], summary["level"], summary["next_level_xp"]), (360, 5, None))
        self.assertIn("Три завершённых проекта", summary["badges"])


if __name__ == "__main__":
    unittest.main()
