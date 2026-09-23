"""Общий каталог доступен всем командам, фильтры меняют только представление."""

from copy import deepcopy
import unittest

from src.catalog import (
    ALL_READINESS,
    ALL_TOPICS,
    READINESS_LEVELS,
    TOPICS,
    catalog_position,
    next_readiness_target,
    normalize_topic,
    published_catalog,
)


def task(task_id, **fields):
    return {"id": task_id, "status": "published", "created_at": "2026-09-01T10:00:00+00:00", **fields}


FULL_FIELDS = {
    "context": "В отделе продаж менеджеры вручную собирают отчёты из нескольких систем.",
    "need": "Сократить время подготовки отчёта для руководителя.",
    "data": "Обезличенные выгрузки продаж за три месяца.",
    "users": "Менеджеры отдела продаж.",
    "constraints": "На работу даётся четыре недели.",
    "expected_result": "Рабочий прототип автоматического отчёта.",
    "success_criteria": "Отчёт собирается менее чем за пять минут.",
    "contact": "sales@example.org",
    "collaboration_format": "Еженедельная встреча с руководителем отдела.",
}


class CatalogTests(unittest.TestCase):
    def test_only_published_tasks_but_all_owners_and_low_scores_are_visible(self):
        cards = [
            task("zero", owner_id="Бизнес А"),
            task("full", owner_id="Бизнес Б", **FULL_FIELDS),
            task("hidden", status="draft", **FULL_FIELDS),
            task("archived", status="archived"),
        ]
        self.assertEqual([card["id"] for card in published_catalog(cards)], ["full", "zero"])
        self.assertEqual(published_catalog(cards)[1]["rating"], 0)

    def test_stale_rating_is_recalculated_before_sorting_and_readiness(self):
        cards = [task("empty", rating=100), task("full", rating=0, **FULL_FIELDS)]
        result = published_catalog(cards)
        self.assertEqual([(card["id"], card["rating"]) for card in result], [("full", 100), ("empty", 0)])
        self.assertEqual([card["readiness_level"] for card in result], ["Приоритетная", "Черновик"])

    def test_equal_ratings_order_by_date_then_id(self):
        cards = [
            task("z", created_at="2026-09-02T10:00:00Z"),
            task("b"),
            task("a"),
            task("invalid", created_at="дата неизвестна"),
            task("missing", created_at=None),
        ]
        self.assertEqual([card["id"] for card in published_catalog(cards)], ["a", "b", "z", "invalid", "missing"])
        self.assertEqual(published_catalog(reversed(cards)), published_catalog(cards))

    def test_date_order_is_actual_time_across_timezones(self):
        cards = [
            task("later", created_at="2026-09-01T10:00:00+00:00"),
            task("earlier", created_at="2026-09-01T12:00:00+05:00"),
        ]
        self.assertEqual([card["id"] for card in published_catalog(cards)], ["earlier", "later"])

    def test_single_topic_and_level_filters_compose(self):
        cards = [
            task("analytics", topic=TOPICS[0], **FULL_FIELDS),
            task("analytics_draft", topic=TOPICS[0]),
            task("education", topic="Образование", **FULL_FIELDS),
        ]
        self.assertEqual([card["id"] for card in published_catalog(cards, topic=TOPICS[0])], ["analytics", "analytics_draft"])
        self.assertEqual([card["id"] for card in published_catalog(cards, readiness="Приоритетная")], ["analytics", "education"])
        self.assertEqual([card["id"] for card in published_catalog(cards, topic=TOPICS[0], readiness="Черновик")], ["analytics_draft"])
        self.assertEqual(published_catalog(cards, topic="Образование", readiness="Рабочая"), [])
        self.assertEqual(len(published_catalog(cards, ALL_TOPICS, ALL_READINESS)), 3)

    def test_legacy_topic_defaults_to_other_without_inferring_content(self):
        cards = [task("legacy", title="Школа и онлайн обучение"), task("invalid", topic="неизвестная тема")]
        self.assertEqual([card["topic"] for card in published_catalog(cards)], ["Другое", "Другое"])
        self.assertEqual(len(published_catalog(cards, topic="Другое")), 2)
        self.assertEqual(published_catalog(cards, topic="Образование"), [])
        for value in (None, "", [], {}, 12):
            self.assertEqual(normalize_topic(value), "Другое")
        for topic in TOPICS:
            self.assertEqual(normalize_topic(topic), topic)

    def test_function_and_returned_nested_values_do_not_mutate_input(self):
        cards = [task("full", rating=0, metadata={"labels": ["подтверждено"]}, **FULL_FIELDS)]
        before = deepcopy(cards)
        result = published_catalog(cards)
        result[0]["metadata"]["labels"].append("изменено")
        result[0]["title"] = "Другое название"
        self.assertEqual(cards, before)

    def test_global_position_does_not_depend_on_filter(self):
        cards = [task("full", topic=TOPICS[0], **FULL_FIELDS), task("low", topic="Образование")]
        self.assertEqual([card["id"] for card in published_catalog(cards, topic="Образование")], ["low"])
        self.assertEqual(catalog_position(cards, "low"), (2, 2))
        self.assertEqual(catalog_position(cards, "full"), (1, 2))

    def test_missing_or_unpublished_position(self):
        cards = [task("live"), task("private", status="draft")]
        self.assertEqual(catalog_position(cards, "private"), (None, 1))
        self.assertEqual(catalog_position(cards, "missing"), (None, 1))
        self.assertEqual(catalog_position([], "missing"), (None, 0))

    def test_iterable_input_and_unknown_filters(self):
        self.assertEqual(len(published_catalog(iter([task("a")]))), 1)
        self.assertEqual(published_catalog([task("a")], topic="ошибка"), [])
        self.assertEqual(published_catalog([task("a")], readiness="ошибка"), [])

    def test_next_goal_boundaries_and_no_extra_level(self):
        cases = [(0, 40, 40), (39, 40, 1), (40, 70, 30), (69, 70, 1), (70, 90, 20), (89, 90, 1), (90, 100, 10), (99, 100, 1)]
        for score, target, remaining in cases:
            with self.subTest(score=score):
                result = next_readiness_target(score)
                self.assertEqual((result["target_score"], result["points_needed"]), (target, remaining))
        self.assertEqual(READINESS_LEVELS, ("Черновик", "Рабочая", "Готовая", "Приоритетная"))
        self.assertEqual(next_readiness_target(99)["label"], "Все поля заполнены")
        self.assertIsNone(next_readiness_target(100))

    def test_next_goal_rejects_invalid_scores(self):
        for value in (-1, 101, 42.5, True, "40", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                next_readiness_target(value)


if __name__ == "__main__":
    unittest.main()
