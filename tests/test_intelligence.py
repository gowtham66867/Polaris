import tempfile
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from polaris_guidance.domain import CaseStore
from polaris_guidance.intelligence import coordination_graph, simulation_evidence


class JourneyIntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.store = CaseStore(Path(self.tempdir.name) / "graph.db")
        self.case = self.store.create_case(
            display_name="Demo",
            reason="Scheduled visit",
            urgency="routine",
            consent_to_coordinate=True,
            target_minutes=45,
        )

    def tearDown(self):
        self.tempdir.cleanup()

    def test_graph_marks_current_stage_and_owner(self):
        case = self.store.update_stage(self.case.id, "triage", "nurse")
        graph = coordination_graph(case, self.store.list_events(case.id))
        triage = next(node for node in graph["nodes"] if node["id"] == "triage")
        self.assertEqual(triage["state"], "current")
        self.assertEqual(triage["owner"], "triage nurse")

    def test_open_barrier_marks_stage_blocked(self):
        self.store.add_event(self.case.id, "nurse", "barrier_reported", "Records pending")
        graph = coordination_graph(self.case, self.store.list_events(self.case.id))
        self.assertEqual(graph["nodes"][0]["state"], "blocked")
        self.assertEqual(len(graph["open_barriers"]), 1)

    def test_elapsed_target_changes_forecast(self):
        old = (datetime.now(UTC) - timedelta(minutes=60)).isoformat()
        late_case = replace(self.case, created_at=old)
        graph = coordination_graph(late_case, self.store.list_events(self.case.id))
        self.assertEqual(graph["forecast"]["status"], "over_target")

    def test_simulation_is_labeled_and_computed(self):
        evidence = simulation_evidence()
        metrics = evidence["metrics"]
        self.assertIn("not clinical", evidence["disclaimer"])
        self.assertEqual(evidence["scenario_count"], 12)
        self.assertGreater(
            metrics["median_time_to_named_owner_baseline_minutes"],
            metrics["median_time_to_named_owner_polaris_minutes"],
        )
        self.assertEqual(metrics["unsafe_action_escapes_in_safety_suite"], 0)


if __name__ == "__main__":
    unittest.main()
