"""AI boundary tests: all requests are mocked; no API keys or network required."""
from __future__ import annotations

import copy
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from openai import APITimeoutError, RateLimitError

from src import ai
from src.models import CARD_FIELDS


DRAFT = "Магазин теряет заказы. Нужно найти причины отказов."
CONTEXT = "Магазин теряет заказы."
NEED = "Нужно найти причины отказов."


def settings(**overrides):
    result = {
        "demo": False, "provider": "auto", "timeout": 7.0,
        "openai_model": "gpt-4o-mini",
        "nvidia_model": "nvidia/nemotron-3-super-120b-a12b",
        "openai_ready": True, "nvidia_ready": True,
    }
    result.update(overrides)
    return result


def payload(*, analysis=True):
    fields = {field: [] for field in CARD_FIELDS}
    fields["context"] = [{"source": "draft", "quote": CONTEXT}]
    fields["need"] = [{"source": "draft", "quote": NEED}]
    result = {"field_sources": fields}
    if analysis:
        result.update(
            missing_fields=["data", "constraints", "contact"],
            questions=[
                {"field": "data", "question": "Какие данные можно получить?"},
                {"field": "constraints", "question": "Какие ограничения есть у задачи?"},
                {"field": "contact", "question": "Кто будет отвечать на вопросы команды?"},
            ],
        )
    return result


class ProviderRoutingTests(unittest.TestCase):
    def setUp(self):
        # Never load the real .env, even when the developer has configured keys.
        self.settings = settings()
        self.config_patch = patch.object(ai, "get_settings", return_value=self.settings)
        self.config_patch.start()
        self.addCleanup(self.config_patch.stop)
        self.request_patch = patch.object(ai, "_request_json", return_value=payload())
        self.request = self.request_patch.start()
        self.addCleanup(self.request_patch.stop)

    def test_auto_returns_openai_without_calling_nvidia(self):
        result = ai.analyze_draft(DRAFT)
        self.assertEqual(result["mode"], "openai")
        self.assertEqual(result["card"]["need"], NEED)
        self.assertEqual(result["attempts"], [])
        self.assertEqual([call.args[0] for call in self.request.call_args_list], ["openai"])

    def test_auto_timeout_moves_to_nvidia(self):
        self.request.side_effect = [
            APITimeoutError(request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions")),
            payload(),
        ]
        result = ai.analyze_draft(DRAFT)
        self.assertEqual(result["mode"], "nvidia")
        self.assertEqual(result["attempts"], [{"provider": "openai", "reason": "timeout"}])
        self.assertEqual([call.args[0] for call in self.request.call_args_list], ["openai", "nvidia"])

    def test_auto_both_fail_returns_local_with_safe_diagnostics(self):
        response = httpx.Response(429, request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"))
        self.request.side_effect = [
            RateLimitError("private provider diagnostic", response=response, body=None),
            RuntimeError("private-key-and-draft-must-not-appear"),
        ]
        result = ai.analyze_draft(DRAFT)
        self.assertEqual(result["mode"], "demo")
        self.assertEqual(result["card"]["context"], DRAFT)
        self.assertEqual(result["attempts"], [
            {"provider": "openai", "reason": "rate_limit"},
            {"provider": "nvidia", "reason": "unavailable"},
        ])
        self.assertNotIn("private", json.dumps(result))
        self.assertGreaterEqual(len(result["questions"]), 3)

    def test_explicit_provider_failure_does_not_call_other_provider(self):
        for provider in ("openai", "nvidia"):
            with self.subTest(provider=provider):
                self.request.reset_mock()
                self.request.side_effect = ValueError("Bad JSON")
                result = ai.analyze_draft(DRAFT, provider=provider)
                self.assertEqual(result["mode"], "demo")
                self.assertEqual(result["reason"], "invalid_response")
                self.assertEqual([call.args[0] for call in self.request.call_args_list], [provider])

    def test_missing_keys_never_make_requests(self):
        self.settings.update(openai_ready=False, nvidia_ready=False)
        result = ai.analyze_draft(DRAFT)
        self.request.assert_not_called()
        self.assertEqual(result["mode"], "demo")
        self.assertEqual(result["attempts"], [
            {"provider": "openai", "reason": "missing_key"},
            {"provider": "nvidia", "reason": "missing_key"},
        ])

    def test_missing_openai_key_can_use_nvidia_in_auto(self):
        self.settings["openai_ready"] = False
        result = ai.analyze_draft(DRAFT)
        self.assertEqual(result["mode"], "nvidia")
        self.assertEqual(result["attempts"], [{"provider": "openai", "reason": "missing_key"}])
        self.assertEqual(self.request.call_args.args[0], "nvidia")

    def test_invalid_evidence_triggers_fallback(self):
        bad = payload()
        bad["field_sources"]["constraints"] = [{"source": "draft", "quote": "Срок четыре недели"}]
        self.request.side_effect = [bad, payload()]
        result = ai.analyze_draft(DRAFT)
        self.assertEqual(result["mode"], "nvidia")
        self.assertEqual(result["attempts"], [{"provider": "openai", "reason": "invalid_response"}])
        self.assertEqual(result["card"]["constraints"], "")

    def test_demo_mode_analyzes_and_builds_without_network(self):
        for explicit, configured in ((None, True), ("demo", False)):
            with self.subTest(explicit=explicit, configured=configured):
                self.settings["demo"] = configured
                baseline = ai.analyze_draft(ai.DEMO_DRAFT, provider=explicit)
                result = ai.build_card(ai.DEMO_DRAFT, ai.DEMO_ANSWERS, provider=explicit)
                self.assertEqual(baseline["mode"], "demo")
                self.assertEqual(result["card"], ai.DEMO_ANSWERS)
                self.assertEqual(result["reason"], "demo_requested")
        self.request.assert_not_called()

    def test_second_request_failure_preserves_verified_card_and_new_answers(self):
        self.request.side_effect = [payload(), RuntimeError("offline")]
        baseline = ai.analyze_draft(DRAFT, provider="openai")
        original = copy.deepcopy(baseline["card"])
        result = ai.build_card(
            DRAFT, {"data": "Есть обезличенные события сайта."},
            provider="openai", known_card=baseline["card"],
        )
        self.assertEqual(result["mode"], "demo")
        self.assertEqual(result["card"]["context"], CONTEXT)
        self.assertEqual(result["card"]["need"], NEED)
        self.assertEqual(result["card"]["data"], "Есть обезличенные события сайта.")
        self.assertEqual(baseline["card"], original)

    def test_fallback_does_not_trust_invented_known_card(self):
        self.settings["demo"] = True
        result = ai.build_card(DRAFT, {}, known_card={"constraints": "Бюджет миллион тенге"})
        self.assertEqual(result["card"]["constraints"], "")
        self.request.assert_not_called()


class PayloadValidationTests(unittest.TestCase):
    def validate(self, raw, *, analysis=True):
        return ai._validate_payload(raw, {"draft": DRAFT}, analysis=analysis)

    def test_valid_quotes_become_exact_card_values(self):
        result = self.validate(payload())
        self.assertEqual(result["card"]["context"], CONTEXT)
        self.assertEqual(result["card"]["need"], NEED)
        self.assertEqual(result["evidence"]["need"], [{"source": "draft", "quote": NEED}])

    def test_json_top_level_and_content_types_are_strict(self):
        for text in ("[]", "null", "true", "1", '"object"', "not JSON", None, {}):
            with self.subTest(text=text), self.assertRaises(ValueError):
                ai._parse_json(text)
        self.assertEqual(ai._parse_json('```json\n{"field_sources": {}}\n```'), {"field_sources": {}})

    def test_invalid_field_and_evidence_types_are_rejected(self):
        invalid_values = (
            None, "text", {}, 1,
            [{"source": "draft", "quote": 123}],
            [{"source": ["draft"], "quote": CONTEXT}],
            [{"source": "draft", "quote": CONTEXT, "summary": "Invented"}],
        )
        for value in invalid_values:
            with self.subTest(value=value):
                raw = payload()
                raw["field_sources"]["context"] = value
                with self.assertRaises(ValueError):
                    self.validate(raw)

    def test_unknown_sources_and_fabricated_facts_are_rejected(self):
        for item in (
            {"source": "answer:contact", "quote": "Иван"},
            {"source": "draft", "quote": "Срок четыре недели"},
            {"source": "draft", "quote": ""},
        ):
            with self.subTest(item=item):
                raw = payload()
                raw["field_sources"]["contact"] = [item]
                with self.assertRaises(ValueError):
                    self.validate(raw)

    def test_unexpected_summary_and_incomplete_shape_are_rejected(self):
        extra = payload()
        extra["card"] = {"contact": "Invented contact"}
        incomplete = payload()
        del incomplete["field_sources"]["contact"]
        empty = payload()
        empty["field_sources"] = {field: [] for field in CARD_FIELDS}
        for raw in (extra, incomplete, empty):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                self.validate(raw)

    def test_missing_fields_and_questions_have_strict_types(self):
        for value in (None, "data", [1], [True], ["unknown"]):
            with self.subTest(missing_fields=value):
                raw = payload()
                raw["missing_fields"] = value
                with self.assertRaises(ValueError):
                    self.validate(raw)
        for value in (None, {}, [], payload()["questions"][:2]):
            with self.subTest(questions=value):
                raw = payload()
                raw["questions"] = value
                with self.assertRaises(ValueError):
                    self.validate(raw)
        for field, value in (("field", 1), ("question", ["A question"]), ("question", True)):
            with self.subTest(field=field, value=value):
                raw = payload()
                raw["questions"][0][field] = value
                with self.assertRaises(ValueError):
                    self.validate(raw)


class RequestBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.sdk_patch = patch("openai.OpenAI")
        self.sdk = self.sdk_patch.start()
        self.addCleanup(self.sdk_patch.stop)
        self.client = self.sdk.return_value.__enter__.return_value
        self.response = SimpleNamespace(choices=[SimpleNamespace(
            finish_reason="stop", message=SimpleNamespace(content='{"ok": true}', refusal=None),
        )])
        self.client.chat.completions.create.return_value = self.response
        self.env_patch = patch.dict("os.environ", {
            "OPENAI_API_KEY": "synthetic-openai-key", "NVIDIA_API_KEY": "synthetic-nvidia-key",
            "OPENAI_BASE_URL": "https://untrusted.example.invalid/v1",
        })
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)

    def request(self, provider="openai"):
        return ai._request_json(provider, settings(), [{"role": "user", "content": "Return JSON"}], {"type": "object"})

    def test_openai_uses_fixed_endpoint_schema_timeout_and_no_retries(self):
        self.assertEqual(self.request(), {"ok": True})
        self.assertEqual(self.sdk.call_args.kwargs, {
            "api_key": "synthetic-openai-key", "base_url": "https://api.openai.com/v1",
            "timeout": 7.0, "max_retries": 0,
        })
        kwargs = self.client.chat.completions.create.call_args.kwargs
        self.assertEqual(kwargs["response_format"]["type"], "json_schema")
        self.assertIs(kwargs["response_format"]["json_schema"]["strict"], True)
        self.assertIs(kwargs["stream"], False)

    def test_nvidia_uses_its_key_and_endpoint_without_unverified_json_mode(self):
        self.assertEqual(self.request("nvidia"), {"ok": True})
        self.assertEqual(self.sdk.call_args.kwargs["base_url"], "https://integrate.api.nvidia.com/v1")
        self.assertEqual(self.sdk.call_args.kwargs["api_key"], "synthetic-nvidia-key")
        kwargs = self.client.chat.completions.create.call_args.kwargs
        self.assertNotIn("response_format", kwargs)
        self.assertEqual(kwargs["extra_body"], {"chat_template_kwargs": {"enable_thinking": False}})

    def test_incomplete_empty_refused_and_non_json_responses_are_rejected(self):
        cases = [
            SimpleNamespace(choices=[]),
            SimpleNamespace(choices=[SimpleNamespace(finish_reason="length", message=SimpleNamespace(content='{"ok": true}'))]),
            SimpleNamespace(choices=[SimpleNamespace(finish_reason="content_filter", message=SimpleNamespace(content='{"ok": true}'))]),
            SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content='{"ok": true}', refusal="Refused"))]),
            SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=None))]),
        ]
        for response in cases:
            with self.subTest(response=response):
                self.client.chat.completions.create.return_value = response
                with self.assertRaises(ValueError):
                    self.request()


class ConnectionProbeTests(unittest.TestCase):
    def test_probe_accepts_only_actual_boolean_true(self):
        with patch.object(ai, "get_settings", return_value=settings()), patch.object(ai, "_request_json") as request:
            for value in (1, 1.0, "true", False, None):
                with self.subTest(value=value):
                    request.return_value = {"ok": value}
                    result = ai.check_connection("openai")
                    self.assertEqual(result["results"], [{"provider": "openai", "ok": False, "reason": "invalid_response"}])
            request.return_value = {"ok": True}
            self.assertEqual(ai.check_connection("openai")["results"], [{"provider": "openai", "ok": True, "reason": ""}])

    def test_probe_no_keys_and_demo_do_not_request(self):
        with patch.object(ai, "get_settings", return_value=settings(openai_ready=False, nvidia_ready=False)), patch.object(ai, "_request_json") as request:
            self.assertEqual(ai.check_connection("demo"), {"results": []})
            result = ai.check_connection("auto")
            self.assertEqual([item["reason"] for item in result["results"]], ["missing_key", "missing_key"])
            request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
