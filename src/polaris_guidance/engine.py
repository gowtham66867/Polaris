from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from .domain import STAGES, Case, Event

RED_FLAG_TERMS = {
    "chest pain",
    "cannot breathe",
    "can't breathe",
    "severe bleeding",
    "unconscious",
    "stroke",
    "seizure",
    "suicidal",
}

STAGE_OWNERS = {
    "arrival": "front desk",
    "registration": "registration team",
    "triage": "triage nurse",
    "clinical_review": "clinical team",
    "diagnostics": "diagnostics team",
    "treatment": "care team",
    "discharge": "discharge coordinator",
}


@dataclass(frozen=True)
class Guidance:
    priority: str
    summary: str
    next_action: str
    owner: str
    rationale: str
    requires_human_approval: bool = True
    clinical_decision: bool = False
    source: str = "workflow"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def elapsed_minutes(case: Case, now: datetime | None = None) -> int:
    start = datetime.fromisoformat(case.created_at)
    current = now or datetime.now(UTC)
    return max(0, int((current - start).total_seconds() // 60))


def contains_red_flag(texts: Iterable[str]) -> bool:
    normalized = " ".join(texts).casefold()
    return any(term in normalized for term in RED_FLAG_TERMS)


def deterministic_guidance(case: Case, events: list[Event]) -> Guidance:
    messages = [case.reason, *(event.message for event in events)]
    if contains_red_flag(messages):
        return Guidance(
            priority="emergency",
            summary="Possible emergency language detected. Do not use the coordination queue.",
            next_action=(
                "Alert the hospital's emergency/triage team immediately and follow the local "
                "emergency protocol. The agent must not diagnose or suggest treatment."
            ),
            owner="triage nurse",
            rationale="A safety rule matched emergency-language indicators.",
        )

    open_barriers = _open_barriers(events)
    waited = elapsed_minutes(case)
    target_exceeded = waited > case.target_minutes
    owner = STAGE_OWNERS[case.stage]

    if open_barriers:
        latest = open_barriers[-1]
        return Guidance(
            priority="high" if target_exceeded else "medium",
            summary=f"A reported barrier is blocking {case.stage.replace('_', ' ')}.",
            next_action=(
                f"Ask {owner} to confirm ownership and resolution time for: {latest.message}"
            ),
            owner=owner,
            rationale="An unresolved barrier is present in the auditable timeline.",
        )

    if target_exceeded:
        return Guidance(
            priority="high",
            summary=f"The case has exceeded its {case.target_minutes}-minute journey target.",
            next_action=f"Request a status update and named next step from the {owner}.",
            owner=owner,
            rationale=f"Elapsed wait is {waited} minutes with no documented blocking reason.",
        )

    next_stage = _next_stage(case.stage)
    if next_stage:
        return Guidance(
            priority="normal",
            summary=f"The patient is currently in {case.stage.replace('_', ' ')}.",
            next_action=(
                f"Confirm readiness criteria with the {owner}, then prepare the handoff to "
                f"{STAGE_OWNERS[next_stage]}."
            ),
            owner=owner,
            rationale="Proactive handoff preparation can reduce avoidable queue time.",
        )

    return Guidance(
        priority="normal",
        summary="The patient journey is at discharge.",
        next_action=(
            "Confirm instructions, follow-up ownership, transport, and patient understanding."
        ),
        owner=owner,
        rationale="A closed-loop discharge reduces uncertainty and repeat coordination.",
    )


def _open_barriers(events: list[Event]) -> list[Event]:
    barriers: list[Event] = []
    for event in events:
        if event.event_type == "barrier_reported":
            barriers.append(event)
        elif event.event_type == "barrier_resolved" and barriers:
            barriers.pop(0)
    return barriers


def _next_stage(stage: str) -> str | None:
    index = STAGES.index(stage)
    return STAGES[index + 1] if index + 1 < len(STAGES) else None
