import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from polaris_guidance.domain import Case, CaseStore
from polaris_guidance.engine import deterministic_guidance


class GuidanceEngineTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.store = CaseStore(Path(self.tempdir.name) / "test.db")

    def tearDown(self):
        self.tempdir.cleanup()

    def create_case(self):
        return self.store.create_case(
            display_name="Demo patient",
            reason="Scheduled outpatient visit",
            urgency="routine",
            consent_to_coordinate=True,
            target_minutes=45,
        )

    def test_open_barrier_names_owner_and_requires_approval(self):
        case = self.create_case()
        case = self.store.update_stage(case.id, "registration", "admin")
        self.store.add_event(case.id, "admin", "barrier_reported", "Insurance confirmation pending")

        guidance = deterministic_guidance(case, self.store.list_events(case.id))

        self.assertEqual(guidance.owner, "registration team")
        self.assertIn("Insurance confirmation pending", guidance.next_action)
        self.assertTrue(guidance.requires_human_approval)
        self.assertFalse(guidance.clinical_decision)

    def test_emergency_language_bypasses_normal_queue_guidance(self):
        case = self.store.create_case(
            display_name="Demo patient",
            reason="Patient says they cannot breathe",
            urgency="urgent",
            consent_to_coordinate=True,
        )

        guidance = deterministic_guidance(case, self.store.list_events(case.id))

        self.assertEqual(guidance.priority, "emergency")
        self.assertIn("immediately", guidance.next_action)
        self.assertIn("must not diagnose", guidance.next_action)

    def test_over_target_requests_status_without_changing_clinical_priority(self):
        case = self.create_case()
        old = (datetime.now(UTC) - timedelta(minutes=90)).isoformat()
        late_case = Case(**{**case.__dict__, "created_at": old})

        guidance = deterministic_guidance(late_case, self.store.list_events(case.id))

        self.assertEqual(guidance.priority, "high")
        self.assertIn("status update", guidance.next_action)
        self.assertFalse(guidance.clinical_decision)

    def test_stage_cannot_move_backward(self):
        case = self.create_case()
        self.store.update_stage(case.id, "triage", "nurse")

        with self.assertRaisesRegex(ValueError, "cannot move backward"):
            self.store.update_stage(case.id, "registration", "admin")


if __name__ == "__main__":
    unittest.main()
