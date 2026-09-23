"""Synthetic seed data meets section 6 and demonstrates all readiness levels."""
from __future__ import annotations

import json
from pathlib import Path
import unittest
from urllib.parse import urlsplit

from src.models import Application, CARD_FIELDS, is_valid_prototype_url
from src.rating import calculate_rating


class SeedDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.seed = json.loads((Path(__file__).resolve().parents[1] / "data" / "seed.json").read_text(encoding="utf-8"))

    def test_minimum_five_of_each_dataset_with_unique_ids(self):
        for collection in ("drafts", "cards", "teams", "applications"):
            with self.subTest(collection=collection):
                rows = self.seed[collection]
                self.assertGreaterEqual(len(rows), 5)
                self.assertEqual(len({row["id"] for row in rows}), len(rows))

    def test_drafts_have_industries_and_different_detail(self):
        drafts = self.seed["drafts"]
        for row in drafts:
            self.assertTrue(row["industry"].strip())
            self.assertTrue(row["text"].strip())
        lengths = [len(row["text"]) for row in drafts]
        self.assertGreater(max(lengths), 4 * min(lengths))

    def test_cards_have_complete_schema_confirmations_and_current_scores(self):
        for row in self.seed["cards"]:
            with self.subTest(card=row["id"]):
                self.assertTrue(set(CARD_FIELDS).issubset(row))
                self.assertTrue(all(isinstance(row[field], str) for field in CARD_FIELDS))
                self.assertEqual(row["status"], "published")
                self.assertTrue(row["confirmed_at"])
                self.assertEqual(row["rating"], calculate_rating(row)["score"])

    def test_all_four_readiness_levels_can_be_demonstrated(self):
        levels = {calculate_rating(row)["level"] for row in self.seed["cards"]}
        self.assertEqual(levels, {"Черновик", "Рабочая", "Готовая", "Приоритетная"})

    def test_team_profiles_have_required_fields_without_sensitive_attributes(self):
        for row in self.seed["teams"]:
            self.assertTrue(row["name"].strip())
            for key in ("interests", "skills", "technologies"):
                self.assertIsInstance(row[key], list)
                self.assertTrue(row[key])
                self.assertTrue(all(isinstance(value, str) and value.strip() for value in row[key]))
            self.assertEqual(set(row), {"id", "name", "interests", "skills", "technologies"})

    def test_proposals_have_timeline_links_and_valid_relations(self):
        task_ids = {row["id"] for row in self.seed["cards"]}
        teams = {row["id"]: row["name"] for row in self.seed["teams"]}
        for row in self.seed["applications"]:
            with self.subTest(application=row["id"]):
                self.assertEqual(Application(**row).to_dict(), row)
                for field in ("team_name", "idea", "plan", "timeline", "prototype_url"):
                    self.assertTrue(row[field].strip())
                self.assertTrue(is_valid_prototype_url(row["prototype_url"]))
                self.assertEqual(urlsplit(row["prototype_url"]).hostname, "example.com")
                self.assertIn(row["task_id"], task_ids)
                self.assertEqual(row["team_name"], teams[row["team_id"]])
                self.assertEqual(row["status"], "pending")


if __name__ == "__main__":
    unittest.main()
