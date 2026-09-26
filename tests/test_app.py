import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import polaris_guidance.app as app_module


class APITests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tempdir.name) / "api.db")
        self.db_patch = patch.object(app_module, "DB_PATH", self.db_path)
        self.db_patch.start()
        self.client_context = TestClient(app_module.app)
        self.client = self.client_context.__enter__()

    def tearDown(self):
        self.client_context.__exit__(None, None, None)
        self.db_patch.stop()
        self.tempdir.cleanup()

    def test_health_and_metrics(self):
        health = self.client.get("/api/health").json()
        self.assertEqual(health["status"], "ok")
        self.assertEqual(health["llm_target"], "anthropic/claude-opus-5")
        self.assertFalse(health["llm_connected"])
        metrics = self.client.get("/api/metrics").json()
        self.assertEqual(metrics["active_cases"], 3)
        self.assertIn("triage", metrics["by_stage"])

    def test_moat_evidence_and_adapter_catalog_are_exposed(self):
        evidence = self.client.get("/api/evidence").json()
        self.assertEqual(evidence["evidence_type"], "synthetic_counterfactual_simulation")
        self.assertEqual(evidence["hospital_adapters"], 2)
        self.assertGreater(evidence["metrics"]["simulated_minutes_saved"], 0)
        hospitals = self.client.get("/api/hospitals").json()
        self.assertEqual({item["standard"] for item in hospitals}, {"FHIR R4", "HL7 v2"})

    def test_ecosystem_endpoints_route_and_isolate_hospitals(self):
        network = self.client.get("/api/ecosystem").json()
        self.assertEqual(len(network["hospitals"]), 2)
        response = self.client.post(
            "/api/patient-agent/route",
            json={
                "patient_id": "api-patient",
                "text": "Please check me in",
                "hospital_id": "stmarys",
                "consent_to_share": True,
                "payload": {"appointment_id": "a1", "insurance": "must-not-pass"},
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["shared_fields"], ["appointment_id"])
        self.assertEqual(body["stripped_fields"], ["insurance"])
        sharing = self.client.get("/api/patient-agent/api-patient/sharing-log").json()
        self.assertEqual(sharing[0]["hospital_id"], "stmarys")

    def test_conflict_resolution_endpoint(self):
        conflicts = self.client.get("/api/patient-agent/demo-patient/conflicts").json()
        response = self.client.post(
            "/api/patient-agent/conflicts/resolve",
            json={"patient_id": "demo-patient", "conflict_id": conflicts[0]["id"]},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "resolved")

    def test_consent_is_required(self):
        response = self.client.post(
            "/api/cases",
            json={
                "display_name": "Demo",
                "reason": "Routine visit",
                "consent_to_coordinate": False,
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_case_lifecycle_and_offline_agent_trace(self):
        created = self.client.post(
            "/api/cases",
            json={
                "display_name": "Test patient",
                "reason": "Routine follow-up",
                "consent_to_coordinate": True,
            },
        )
        self.assertEqual(created.status_code, 201)
        case_id = created.json()["id"]
        event = self.client.post(
            f"/api/cases/{case_id}/events",
            json={
                "actor": "nurse",
                "event_type": "barrier_reported",
                "message": "Transport pending",
            },
        )
        self.assertEqual(event.status_code, 201)
        graph = self.client.get(f"/api/cases/{case_id}/graph").json()
        self.assertEqual(graph["open_barriers"][0]["message"], "Transport pending")
        self.assertEqual(graph["nodes"][0]["id"], "arrival")

        with patch.dict("os.environ", {"POLARIS_HERMES_API_KEY": ""}):
            result = self.client.post(f"/api/cases/{case_id}/guide")
        self.assertEqual(result.status_code, 200)
        body = result.json()
        self.assertEqual(body["run_status"], "fallback")
        self.assertTrue(body["guidance"]["requires_human_approval"])
        self.assertTrue(body["run_id"].startswith("RUN-"))

        decision = self.client.post(
            f"/api/cases/{case_id}/decision",
            json={
                "guidance_event_id": body["event_id"],
                "actor": "nurse",
                "approved": True,
            },
        )
        self.assertEqual(decision.json()["event_type"], "guidance_approved")
        duplicate = self.client.post(
            f"/api/cases/{case_id}/decision",
            json={
                "guidance_event_id": body["event_id"],
                "actor": "nurse",
                "approved": False,
            },
        )
        self.assertEqual(duplicate.status_code, 400)

        resolved = self.client.post(
            f"/api/cases/{case_id}/barriers/resolve",
            json={"actor": "nurse", "resolution": "Transport confirmed"},
        )
        self.assertEqual(resolved.status_code, 200)
        self.assertEqual(self.client.get(f"/api/cases/{case_id}/graph").json()["open_barriers"], [])
        no_barrier = self.client.post(
            f"/api/cases/{case_id}/barriers/resolve",
            json={"actor": "nurse", "resolution": "Again"},
        )
        self.assertEqual(no_barrier.status_code, 400)

    def test_security_headers_and_request_id(self):
        response = self.client.get("/api/health", headers={"X-Request-ID": "trace-123"})
        self.assertEqual(response.headers["x-request-id"], "trace-123")
        self.assertEqual(response.headers["x-frame-options"], "DENY")
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_missing_case_and_invalid_event_are_rejected(self):
        self.assertEqual(self.client.get("/api/cases/missing").status_code, 404)
        case_id = self.client.get("/api/cases").json()[0]["id"]
        response = self.client.post(
            f"/api/cases/{case_id}/events",
            json={"actor": "hacker", "event_type": "note", "message": "x"},
        )
        self.assertEqual(response.status_code, 400)

    def test_stage_validation_is_exposed_as_bad_request(self):
        case_id = self.client.get("/api/cases").json()[0]["id"]
        response = self.client.post(
            f"/api/cases/{case_id}/stage",
            json={"stage": "arrival", "actor": "nurse"},
        )
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
