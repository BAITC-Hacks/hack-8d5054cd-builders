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

    def test_explicit_data_absence_does_not_earn_points(self):
        for value in (
            "Доступных данных пока нет.",
            "Данных пока нет.",
            "Нет доступных материалов.",
            "Данные пока отсутствуют.",
            "Материалы не предоставлены.",
            "Мы не готовы передать данные.",
            "Мы не можем предоставить материалы.",
            "Нет доступа к данным.",
            "Данных нет, соберём позже после встречи.",
            "Данных нет. Источники уточним позже.",
            "Данных нет, сбор планируется через месяц.",
            "Данных нет, пока не планируем собирать.",
            "Данных нет, документов тоже нет.",
        ):
            with self.subTest(value=value):
                result = calculate_rating({"data": value})
                self.assertEqual(result["score"], 0)
                hint = next(item for item in result["improvements"] if item["field"] == "data")
                self.assertEqual(hint["potential_points"], 20)
                self.assertIn("что и как соберёте", hint["hint"])

    def test_absence_with_named_materials_or_collection_plan_is_preserved(self):
        for value in (
            "Данных нет, соберём ответы покупателей через опрос.",
            "Нет данных о продажах, но есть выгрузка остатков за месяц.",
            "Данных пока нет; есть журнал смен на бумаге.",
            "Данных нет, соберём фото витрин.",
            "Материалы отсутствуют, проведём интервью с управляющими.",
            "Не все данные доступны, есть обезличенная выгрузка событий сайта.",
            "Мы не готовы передать данные, но есть обезличенная выгрузка событий сайта.",
        ):
            with self.subTest(value=value):
                self.assertEqual(calculate_rating({"data": value})["score"], 20)

    def test_vague_acceptance_wishes_do_not_earn_full_weight(self):
        for value in (
            "Нужно, чтобы всё работало хорошо и было удобно.",
            "Всё должно работать быстро, качественно и без проблем.",
            "Нужно, чтобы всё работало хорошо на 100% и было удобно.",
            "Хочется, чтобы было удобно пользоваться сервисом.",
        ):
            with self.subTest(value=value):
                self.assertEqual(calculate_rating({"success_criteria": value})["score"], 0)
        result = calculate_rating({"success_criteria": "Нужно повысить конверсию заказов."})
        self.assertEqual(result["score"], 7)
        hint = next(item for item in result["improvements"] if item["field"] == "success_criteria")
        self.assertEqual(hint["potential_points"], 8)
        self.assertIn("порог метрики", hint["hint"])
        self.assertIn("способ проверки", hint["hint"])

    def test_observable_criteria_and_negation_in_other_fields_are_preserved(self):
        for value in (
            "Ни одного потерянного заказа при повторной отправке формы.",
            "Пользователь оформляет заказ без помощи сотрудника на проверке прототипа.",
            "Нужно повысить конверсию заказов на 5% в эксперименте.",
            "Отчёт собирается менее чем за пять минут.",
            "Работает удобно: покупатель проходит пять сценариев оформления.",
        ):
            with self.subTest(value=value):
                self.assertEqual(calculate_rating({"success_criteria": value})["score"], 15)
        self.assertEqual(calculate_rating({"constraints": "Доступных данных пока нет."})["score"], 10)
        self.assertEqual(calculate_rating({"constraints": "Персональные данные не предоставлены; используем обезличенные события."})["score"], 10)

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
