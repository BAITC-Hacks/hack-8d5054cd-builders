"""Checks for the deterministic completeness score and common empty answers."""

from copy import deepcopy
import json
from pathlib import Path
import unittest

from src.rating import FIELD_WEIGHTS, calculate_rating


FULL_CARD = {
    "title": "Улучшение оформления заказа",
    "context": "Покупатели интернет-магазина уходят во время оформления заказа.",
    "need": "Найти проблемные этапы и предложить улучшения оформления.",
    "data": "Обезличенные события сайта за три месяца.",
    "expected_result": "Рабочий прототип оформления заказа и анализ воронки.",
    "success_criteria": "Пять проверочных сценариев заказа проходят успешно.",
    "constraints": "Четыре недели, без персональных данных покупателей.",
    "users": "Аналитики и руководитель интернет-магазина.",
    "contact": "Руководитель интернет-магазина.",
    "collaboration_format": "Онлайн-встреча один раз в неделю.",
}


class RatingTests(unittest.TestCase):
    def test_group_weights_and_full_card(self):
        result = calculate_rating(FULL_CARD)
        self.assertEqual(result["score"], 100)
        self.assertEqual(result["improvements"], [])
        self.assertEqual(
            [(row["earned"], row["possible"]) for row in result["breakdown"]],
            [(20, 20), (20, 20), (15, 15), (15, 15), (10, 10), (10, 10), (10, 10)],
        )

    def test_empty_card_and_title_do_not_earn_points(self):
        result = calculate_rating({"title": "Достаточно подробный заголовок"})
        self.assertEqual(result["score"], 0)
        self.assertEqual(sum(item["potential_points"] for item in result["improvements"]), 100)

    def test_short_answers_keep_half_weights_and_round_down(self):
        for field, weight in FIELD_WEIGHTS.items():
            with self.subTest(field=field):
                result = calculate_rating({field: "План"})
                self.assertEqual(result["score"], weight // 2)

    def test_detail_length_threshold_is_unchanged(self):
        self.assertEqual(len("Продажи за год"), 14)
        self.assertEqual(len("Продажи за день"), 15)
        self.assertEqual(calculate_rating({"data": "Продажи за год"})["score"], 10)
        self.assertEqual(calculate_rating({"data": "Продажи за день"})["score"], 20)

    def test_level_boundaries(self):
        cases = [
            (39, "Черновик", {"data": FULL_CARD["data"], "expected_result": "План", "success_criteria": "План", "contact": FULL_CARD["contact"]}),
            (40, "Рабочая", {field: FULL_CARD[field] for field in ("data", "context", "need")}),
            (69, "Рабочая", {**{field: FULL_CARD[field] for field in ("context", "need", "data", "constraints", "contact")}, "expected_result": "План", "success_criteria": "План"}),
            (70, "Готовая", {field: FULL_CARD[field] for field in ("context", "need", "data", "expected_result", "success_criteria")}),
            (89, "Готовая", {**FULL_CARD, "constraints": "План", "contact": "План", "collaboration_format": "План"}),
            (90, "Приоритетная", {**FULL_CARD, "need": ""}),
            (100, "Приоритетная", FULL_CARD),
        ]
        for score, level, card in cases:
            with self.subTest(score=score):
                result = calculate_rating(card)
                self.assertEqual((result["score"], result["level"]), (score, level))

    def test_placeholders_ignore_case_whitespace_and_punctuation(self):
        for value in ("не указано", "Не указано.", "  НЕ   УКАЗАНО!!!  ", "Н/Д.", "—", "???", "___", "Нет данных.", "TBD..."):
            with self.subTest(value=value):
                self.assertEqual(calculate_rating({field: value for field in FIELD_WEIGHTS})["score"], 0)

    def test_deferred_answers_are_empty(self):
        for value in ("Уточним позже после встречи", "Уточним позже после встречи.", "Данные уточним после созвона", "Сообщим позднее", "Согласуем на встрече с бизнесом"):
            with self.subTest(value=value):
                self.assertEqual(calculate_rating({field: value for field in FIELD_WEIGHTS})["score"], 0)

    def test_obvious_garbage_and_repeated_words_are_empty(self):
        for value in ("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "яяяяяяяя", "asdfgh", "ЙЦУКЕН", "abcabcabcabc", "данные данные данные данные", "ответ, ответ, ответ", "!!!???---___"):
            with self.subTest(value=value):
                self.assertEqual(calculate_rating({field: value for field in FIELD_WEIGHTS})["score"], 0)

    def test_meaningful_negative_answers_and_addresses_are_preserved(self):
        cases = [
            ("constraints", "Ограничений нет", 10),
            ("data", "Данных нет, соберём ответы покупателей через опрос.", 20),
            ("data", "Нет данных, соберём обезличенные события сайта.", 20),
            ("constraints", "Уточним позже после встречи; пока срок работы четыре недели.", 10),
            ("contact", "team@team.team", 5),
            ("contact", "+7 701 234 56 78", 5),
        ]
        for field, value, points in cases:
            with self.subTest(field=field, value=value):
                self.assertEqual(calculate_rating({field: value})["score"], points)

    def test_non_string_values_are_not_filled_fields(self):
        for value in (None, False, 12345, ["данные"], {"value": "данные"}):
            with self.subTest(value=value):
                self.assertEqual(calculate_rating({"data": value})["score"], 0)

    def test_function_is_deterministic_and_does_not_mutate_input(self):
        card = {**FULL_CARD, "data": "Не указано.", "metadata": {"tags": ["демо"]}}
        before = deepcopy(card)
        first = calculate_rating(card)
        self.assertEqual(first, calculate_rating(card))
        self.assertEqual(card, before)
        first["breakdown"][0]["earned"] = -1
        self.assertNotEqual(first, calculate_rating(card))

    def test_existing_seed_ratings_are_preserved(self):
        path = Path(__file__).resolve().parents[1] / "data" / "seed.json"
        seed = json.loads(path.read_text(encoding="utf-8"))
        for card in seed["cards"]:
            with self.subTest(card=card["id"]):
                self.assertEqual(calculate_rating(card)["score"], card["rating"])


if __name__ == "__main__":
    unittest.main()
