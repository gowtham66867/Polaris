from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from .domain import STAGES, Case, Event
from .engine import STAGE_OWNERS, elapsed_minutes

EXPECTED_STAGE_MINUTES = {
    "arrival": 4,
    "registration": 8,
    "triage": 10,
    "clinical_review": 15,
    "diagnostics": 25,
    "treatment": 20,
    "discharge": 10,
}


def open_barriers(events: list[Event]) -> list[Event]:
    barriers: list[Event] = []
    for event in events:
        if event.event_type == "barrier_reported":
            barriers.append(event)
        elif event.event_type == "barrier_resolved" and barriers:
            barriers.pop(0)
    return barriers


def coordination_graph(case: Case, events: list[Event]) -> dict[str, object]:
    current_index = STAGES.index(case.stage)
    barriers = open_barriers(events)
    elapsed = elapsed_minutes(case)
    remaining = sum(EXPECTED_STAGE_MINUTES[stage] for stage in STAGES[current_index:])
    projected_total = elapsed + remaining
    if elapsed > case.target_minutes:
        forecast_status = "over_target"
    elif projected_total > case.target_minutes:
        forecast_status = "at_risk"
    else:
        forecast_status = "on_track"

    nodes = []
    for index, stage in enumerate(STAGES):
        state = "complete" if index < current_index else "upcoming"
        if index == current_index:
            state = "blocked" if barriers else "current"
        nodes.append(
            {
                "id": stage,
                "label": stage.replace("_", " ").title(),
                "owner": STAGE_OWNERS[stage],
                "state": state,
                "expected_minutes": EXPECTED_STAGE_MINUTES[stage],
            }
        )
    return {
        "case_id": case.id,
        "nodes": nodes,
        "edges": [
            {"from": STAGES[index], "to": STAGES[index + 1], "type": "handoff"}
            for index in range(len(STAGES) - 1)
        ],
        "open_barriers": [
            {"id": event.id, "message": event.message, "reported_by": event.actor}
            for event in barriers
        ],
        "forecast": {
            "status": forecast_status,
            "elapsed_minutes": elapsed,
            "projected_total_minutes": projected_total,
            "target_minutes": case.target_minutes,
            "next_owner": STAGE_OWNERS[case.stage],
        },
    }


@dataclass(frozen=True)
class SimulationScenario:
    hospital: str
    barrier: str
    baseline_detection: int
    baseline_routing: int
    polaris_detection: int
    polaris_approval: int


SCENARIOS = (
    SimulationScenario("Northstar FHIR", "missing records", 24, 13, 3, 4),
    SimulationScenario("Northstar FHIR", "diagnostic queue", 31, 16, 4, 5),
    SimulationScenario("Northstar FHIR", "transport unavailable", 28, 12, 3, 4),
    SimulationScenario("Northstar FHIR", "discharge ownership", 35, 18, 5, 5),
    SimulationScenario("Northstar FHIR", "authorization pending", 42, 21, 4, 6),
    SimulationScenario("Northstar FHIR", "room turnover", 26, 11, 3, 4),
    SimulationScenario("Lakeside HL7", "missing records", 37, 17, 5, 5),
    SimulationScenario("Lakeside HL7", "diagnostic queue", 44, 19, 5, 6),
    SimulationScenario("Lakeside HL7", "transport unavailable", 33, 14, 4, 5),
    SimulationScenario("Lakeside HL7", "discharge ownership", 39, 20, 5, 6),
    SimulationScenario("Lakeside HL7", "authorization pending", 48, 23, 5, 7),
    SimulationScenario("Lakeside HL7", "room turnover", 29, 14, 4, 5),
)


def simulation_evidence() -> dict[str, object]:
    baseline = [scenario.baseline_detection + scenario.baseline_routing for scenario in SCENARIOS]
    polaris = [scenario.polaris_detection + scenario.polaris_approval for scenario in SCENARIOS]
    baseline_median = int(median(baseline))
    polaris_median = int(median(polaris))
    return {
        "evidence_type": "synthetic_counterfactual_simulation",
        "disclaimer": "Hackathon simulation; not clinical or production performance evidence.",
        "scenario_count": len(SCENARIOS),
        "hospital_adapters": 2,
        "metrics": {
            "median_time_to_named_owner_baseline_minutes": baseline_median,
            "median_time_to_named_owner_polaris_minutes": polaris_median,
            "simulated_minutes_saved": baseline_median - polaris_median,
            "ownership_gaps_baseline": len(SCENARIOS),
            "ownership_gaps_polaris": 0,
            "unsafe_action_escapes_in_safety_suite": 0,
            "safety_scenarios": 8,
        },
        "method": {
            "baseline": "Barrier discovery plus manual routing delay.",
            "polaris": "Event detection plus human approval delay.",
            "source": "Versioned synthetic scenarios in polaris_guidance.intelligence.SCENARIOS.",
        },
    }
