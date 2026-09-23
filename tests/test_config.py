"""Configuration checks use only a temporary file and isolated environment."""

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from src import config


class ConfigTests(unittest.TestCase):
    def setUp(self):
        temporary_directory = self.enterContext(TemporaryDirectory())
        self.env_path = Path(temporary_directory) / ".env"
        self.enterContext(patch.object(config, "ENV_PATH", self.env_path))
        self.enterContext(patch.object(config, "_file_values", {}))
        self.enterContext(patch.dict(os.environ, {}, clear=True))

    def write_env(self, text):
        self.env_path.write_text(text, encoding="utf-8")

    def test_loads_values_from_temporary_file(self):
        self.write_env(
            "DEMO_MODE=false\nAI_PROVIDER=nvidia\nAI_TIMEOUT_SECONDS=30\n"
            "OPENAI_MODEL=test-openai-model\nNVIDIA_MODEL=test-nvidia-model\n"
            "OPENAI_API_KEY=test-openai-secret\nNVIDIA_API_KEY=test-nvidia-secret\n"
        )
        settings = config.get_settings()
        self.assertFalse(settings["demo"])
        self.assertEqual(settings["provider"], "nvidia")
        self.assertEqual(settings["timeout"], 30.0)
        self.assertEqual(settings["openai_model"], "test-openai-model")
        self.assertEqual(settings["nvidia_model"], "test-nvidia-model")
        self.assertTrue(settings["openai_ready"])
        self.assertTrue(settings["nvidia_ready"])
        self.assertEqual(os.getenv("OPENAI_API_KEY"), "test-openai-secret")

    def test_file_owned_values_refresh_after_edit(self):
        self.write_env("AI_PROVIDER=openai\nOPENAI_MODEL=model-one\nOPENAI_API_KEY=secret-one\n")
        config.get_settings()
        self.write_env("AI_PROVIDER=nvidia\nOPENAI_MODEL=model-two\nOPENAI_API_KEY=secret-two\n")
        updated = config.get_settings()
        self.assertEqual(updated["provider"], "nvidia")
        self.assertEqual(updated["openai_model"], "model-two")
        self.assertEqual(os.getenv("OPENAI_API_KEY"), "secret-two")
        self.assertEqual(config._file_values["OPENAI_MODEL"], "model-two")

    def test_removed_file_values_are_removed_from_environment(self):
        self.write_env("AI_PROVIDER=nvidia\nAI_TIMEOUT_SECONDS=31\nOPENAI_API_KEY=test-secret\n")
        config.get_settings()
        self.write_env("")
        updated = config.get_settings()
        for key in ("AI_PROVIDER", "AI_TIMEOUT_SECONDS", "OPENAI_API_KEY"):
            self.assertNotIn(key, os.environ)
            self.assertNotIn(key, config._file_values)
        self.assertEqual(updated["provider"], "auto")
        self.assertEqual(updated["timeout"], 20.0)
        self.assertFalse(updated["openai_ready"])

    def test_deleted_file_removes_previously_loaded_values(self):
        self.write_env("NVIDIA_API_KEY=test-secret\nDEMO_MODE=false\n")
        config.get_settings()
        self.env_path.unlink()
        updated = config.get_settings()
        self.assertFalse(updated["nvidia_ready"])
        self.assertTrue(updated["demo"])
        self.assertNotIn("NVIDIA_API_KEY", os.environ)

    def test_explicit_process_environment_has_priority(self):
        os.environ.update({
            "AI_PROVIDER": "openai",
            "OPENAI_API_KEY": "process-secret",
            "OPENAI_MODEL": "process-model",
            "DEMO_MODE": "false",
        })
        self.write_env(
            "AI_PROVIDER=nvidia\nOPENAI_API_KEY=file-secret\n"
            "OPENAI_MODEL=file-model\nDEMO_MODE=true\n"
        )
        settings = config.get_settings()
        self.assertEqual(settings["provider"], "openai")
        self.assertEqual(settings["openai_model"], "process-model")
        self.assertFalse(settings["demo"])
        self.assertEqual(os.getenv("OPENAI_API_KEY"), "process-secret")
        self.write_env("")
        config.get_settings()
        self.assertEqual(os.getenv("OPENAI_API_KEY"), "process-secret")
        self.assertEqual(os.getenv("OPENAI_MODEL"), "process-model")

    def test_later_process_override_survives_file_updates_and_removal(self):
        self.write_env("OPENAI_MODEL=file-model\n")
        config.get_settings()
        os.environ["OPENAI_MODEL"] = "process-override"
        self.write_env("OPENAI_MODEL=changed-file-model\n")
        self.assertEqual(config.get_settings()["openai_model"], "process-override")
        self.write_env("")
        self.assertEqual(config.get_settings()["openai_model"], "process-override")

    def test_invalid_provider_and_timeout_fall_back(self):
        self.write_env("AI_PROVIDER=unknown-provider\nAI_TIMEOUT_SECONDS=not-a-number\n")
        settings = config.get_settings()
        self.assertEqual(settings["provider"], "auto")
        self.assertEqual(settings["timeout"], 20.0)

    def test_nonfinite_timeout_falls_back(self):
        for value in ("nan", "NaN", "inf", "-inf", "Infinity"):
            with self.subTest(value=value):
                self.write_env(f"AI_TIMEOUT_SECONDS={value}\n")
                self.assertEqual(config.get_settings()["timeout"], 20.0)

    def test_finite_timeout_is_bounded(self):
        for value, expected in (("1", 3.0), ("3", 3.0), ("12.5", 12.5), ("60", 60.0), ("999", 60.0)):
            with self.subTest(value=value):
                self.write_env(f"AI_TIMEOUT_SECONDS={value}\n")
                self.assertEqual(config.get_settings()["timeout"], expected)

    def test_blank_models_use_defaults_and_blank_keys_are_not_ready(self):
        self.write_env('OPENAI_MODEL="  "\nNVIDIA_MODEL=""\nOPENAI_API_KEY=" "\nNVIDIA_API_KEY=\n')
        settings = config.get_settings()
        self.assertEqual(settings["openai_model"], "gpt-4o-mini")
        self.assertEqual(settings["nvidia_model"], "nvidia/nemotron-3-super-120b-a12b")
        self.assertFalse(settings["openai_ready"])
        self.assertFalse(settings["nvidia_ready"])

    def test_public_settings_do_not_contain_secrets(self):
        self.write_env("OPENAI_API_KEY=private-test-openai\nNVIDIA_API_KEY=private-test-nvidia\n")
        settings = config.get_settings()
        serialized = json.dumps(settings)
        self.assertNotIn("private-test-openai", serialized)
        self.assertNotIn("private-test-nvidia", serialized)
        self.assertEqual(set(settings), {
            "demo", "provider", "timeout", "openai_model", "nvidia_model",
            "openai_ready", "nvidia_ready",
        })
        self.assertTrue(settings["openai_ready"])
        self.assertTrue(settings["nvidia_ready"])

    def test_unrelated_file_values_do_not_enter_process_environment(self):
        self.write_env("UNRELATED_SETTING=ignore-me\n")
        config.get_settings()
        self.assertNotIn("UNRELATED_SETTING", os.environ)


if __name__ == "__main__":
    unittest.main()
