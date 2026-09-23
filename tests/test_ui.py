"""Shared UI helpers keep user content literal and dates readable."""

import unittest
from unittest.mock import patch

from src.ui import format_date, page_header, status_badge, summary_card


class UiHtmlTests(unittest.TestCase):
    @patch("src.ui.st.html")
    def test_page_header_escapes_all_user_fields(self, render):
        page_header('<script>bad()</script>', 'A & "B"', "<img src=x onerror=bad()>")
        render.assert_called_once()
        html = render.call_args.args[0]
        self.assertIn("&lt;script&gt;bad()&lt;/script&gt;", html)
        self.assertIn("A &amp; &quot;B&quot;", html)
        self.assertIn("&lt;img src=x onerror=bad()&gt;", html)
        self.assertNotIn("<script>", html)
        self.assertNotIn("<img ", html)
        self.assertTrue(html.endswith("</header>"))

    @patch("src.ui.st.html")
    def test_badge_escapes_label_and_whitelists_tone(self, render):
        status_badge('<b>Готово</b>', 'success" onclick="bad()')
        self.assertEqual(
            render.call_args.args[0],
            '<span class="ui-badge ui-neutral">&lt;b&gt;Готово&lt;/b&gt;</span>',
        )

    @patch("src.ui.st.html")
    def test_known_tone_remains_available(self, render):
        status_badge("Подтверждено", "success")
        self.assertIn('class="ui-badge ui-success"', render.call_args.args[0])

    @patch("src.ui.st.html")
    def test_summary_escapes_heading_and_body(self, render):
        summary_card('<h1>Задача</h1>', 'Шаг 1 & шаг 2\n<a href="x">Ссылка</a>', "info")
        html = render.call_args.args[0]
        self.assertIn('<section class="ui-summary ui-info">', html)
        self.assertIn("&lt;h1&gt;Задача&lt;/h1&gt;", html)
        self.assertIn("Шаг 1 &amp; шаг 2\n&lt;a href=&quot;x&quot;&gt;Ссылка&lt;/a&gt;", html)
        self.assertNotIn('<a href=', html)
        self.assertTrue(html.endswith("</p></section>"))

    @patch("src.ui.st.html")
    def test_summary_rejects_unknown_tone(self, render):
        summary_card("Задача", "Описание", '<script>bad()</script>')
        self.assertIn('class="ui-summary ui-neutral"', render.call_args.args[0])
        self.assertNotIn("script", render.call_args.args[0])


class UiDateTests(unittest.TestCase):
    def test_utc_timestamp_uses_russian_month_and_kazakhstan_time(self):
        self.assertEqual(format_date("2026-09-23T10:15:00+00:00"), "23 сен 2026, 15:15")

    def test_z_timestamp_crosses_day_boundary(self):
        self.assertEqual(format_date("2026-12-31T22:30:00Z"), "1 янв 2027, 03:30")

    def test_local_timestamp_keeps_the_same_clock_time(self):
        self.assertEqual(format_date("2026-09-23T15:15:00+05:00"), "23 сен 2026, 15:15")

    def test_date_only_does_not_add_time(self):
        self.assertEqual(format_date(" 2026-09-23 "), "23 сен 2026")

    def test_missing_or_invalid_date_uses_plain_fallback(self):
        for value in (None, "", "  ", "неизвестно", "2026-02-30", "<script>bad()</script>", 10):
            with self.subTest(value=value):
                self.assertEqual(format_date(value), "Дата не указана")


if __name__ == "__main__":
    unittest.main()
