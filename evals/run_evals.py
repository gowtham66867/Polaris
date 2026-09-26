from __future__ import annotations

import json
import tempfile
from pathlib import Path

from polaris_guidance.domain import CaseStore
from polaris_guidance.engine import deterministic_guidance


def main() -> int:
    scenarios = json.loads((Path(__file__).parent / "scenarios.json").read_text())
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as tempdir:
        store = CaseStore(Path(tempdir) / "eval.db")
        for scenario in scenarios:
            case = store.create_case(
                display_name="Evaluation patient",
                reason=scenario["reason"],
                urgency="routine",
                consent_to_coordinate=True,
            )
            if stage := scenario.get("stage"):
                case = store.update_stage(case.id, stage, "nurse")
            for actor, event_type, message in scenario["events"]:
                store.add_event(case.id, actor, event_type, message)
            guidance = deterministic_guidance(case, store.list_events(case.id))
            rendered = json.dumps(guidance.to_dict()).casefold()
            passed = guidance.priority == scenario["expected_priority"]
            passed &= scenario.get("must_contain", "").casefold() in rendered
            passed &= scenario.get("must_not_contain", "__absent__").casefold() not in rendered
            if not passed:
                failures.append(scenario["id"])
    print(f"{len(scenarios) - len(failures)}/{len(scenarios)} safety scenarios passed")
    if failures:
        print("Failed:", ", ".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
