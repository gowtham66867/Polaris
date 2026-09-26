import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import polaris_guidance.app as app_module


class ApproveExecutesTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(app_module, "DB_PATH", str(Path(self.tempdir.name) / "a.db"))
        self.db_patch.start()
        self.env = patch.dict(os.environ, {}, clear=False)
        self.env.start()
        os.environ.pop("OPENAI_API_KEY", None)
        os.environ.pop("POLARIS_HERMES_API_KEY", None)
        self.ctx = TestClient(app_module.app)
        self.client = self.ctx.__enter__()

    def tearDown(self):
        self.ctx.__exit__(None, None, None)
        self.env.stop()
        self.db_patch.stop()
        self.tempdir.cleanup()

    def _case(self, name):
        return next(c for c in self.client.get("/api/cases").json() if c["display_name"] == name)

    def _approve(self, case_id):
        guidance = self.client.post(f"/api/cases/{case_id}/guide").json()
        return self.client.post(
            f"/api/cases/{case_id}/decision",
            json={"guidance_event_id": guidance["event_id"], "actor": "nurse", "approved": True},
        ).json()

    def test_approval_executes_handoff_and_advances_stage(self):
        case = self._case("Safety challenge (demo)")
        self.assertEqual(case["stage"], "registration")
        result = self._approve(case["id"])
        self.assertEqual(result["action"]["action_type"], "handoff")
        self.assertEqual(result["action"]["new_stage"], "triage")
        detail = self.client.get(f"/api/cases/{case['id']}").json()
        self.assertEqual(detail["case"]["stage"], "triage")
        self.assertIn("action_executed", [e["event_type"] for e in detail["events"]])

    def test_approval_with_open_barrier_escalates_without_moving(self):
        case = self._case("Maya (demo)")
        result = self._approve(case["id"])
        self.assertEqual(result["action"]["action_type"], "barrier_escalation")
        self.assertEqual(self._case("Maya (demo)")["stage"], "triage")

    def test_dismissal_executes_nothing(self):
        case = self._case("Arun (demo)")
        guidance = self.client.post(f"/api/cases/{case['id']}/guide").json()
        result = self.client.post(
            f"/api/cases/{case['id']}/decision",
            json={"guidance_event_id": guidance["event_id"], "actor": "nurse", "approved": False},
        ).json()
        self.assertIsNone(result["action"])
        self.assertEqual(self._case("Arun (demo)")["stage"], "diagnostics")

    def test_needs_attention_counts_barriers_and_at_risk_forecasts(self):
        metrics = self.client.get("/api/metrics").json()
        flagged = {
            c["display_name"] for c in self.client.get("/api/cases").json() if c["needs_attention"]
        }
        self.assertEqual(flagged, {"Maya (demo)", "Arun (demo)"})
        self.assertEqual(metrics["needs_attention"], 2)


class ProviderSelectionTests(unittest.TestCase):
    def test_openai_key_selects_openai_provider(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test"}, clear=True):
            settings = app_module.llm_settings()
        self.assertEqual(settings["provider"], "openai")
        self.assertEqual(settings["base_url"], "https://api.openai.com/v1")

    def test_hermes_preferred_when_configured(self):
        env = {"OPENAI_API_KEY": "a", "POLARIS_HERMES_API_KEY": "b"}
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(app_module.llm_settings()["provider"], "hermes")

    def test_no_keys_falls_back_to_hermes_offline(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = app_module.llm_settings()
        self.assertEqual(settings["provider"], "hermes")
        self.assertEqual(settings["api_key"], "")


if __name__ == "__main__":
    unittest.main()
