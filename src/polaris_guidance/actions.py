"""Executes a coordination action after a hospital team member approves it.

Every action is non-clinical workflow coordination (handoffs, owner notifications,
escalation to the hospital's own protocol) and is written to the auditable timeline.
Nothing here runs without an explicit human approval.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .domain import STAGES, Case, CaseStore, Event
from .engine import STAGE_OWNERS, elapsed_minutes
from .intelligence import open_barriers


@dataclass(frozen=True)
class ExecutedAction:
    action_type: str
    message: str
    owner: str
    new_stage: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def execute_approved_action(
    store: CaseStore,
    case: Case,
    events: list[Event],
    guidance: dict[str, object],
    approver: str,
    guidance_event_id: str,
) -> ExecutedAction:
    owner = str(guidance.get("owner") or STAGE_OWNERS[case.stage])
    barriers = open_barriers(events)
    index = STAGES.index(case.stage)
    next_stage = STAGES[index + 1] if index + 1 < len(STAGES) else None

    if guidance.get("priority") == "emergency":
        action = ExecutedAction(
            action_type="emergency_escalation",
            message=(
                f"Emergency alert routed to {owner} per local protocol; "
                "coordination queue bypassed."
            ),
            owner=owner,
        )
    elif barriers:
        action = ExecutedAction(
            action_type="barrier_escalation",
            message=(
                f"Coordination request sent to {owner}: confirm owner and resolution time "
                f"for '{barriers[-1].message}'."
            ),
            owner=owner,
        )
    elif elapsed_minutes(case) > case.target_minutes:
        action = ExecutedAction(
            action_type="status_request",
            message=f"Status update and named next step requested from {owner}.",
            owner=owner,
        )
    elif next_stage:
        next_owner = STAGE_OWNERS[next_stage]
        store.update_stage(case.id, next_stage, approver)
        action = ExecutedAction(
            action_type="handoff",
            message=(
                f"Handoff executed: {STAGE_OWNERS[case.stage]} → {next_owner}. "
                f"{next_owner.capitalize()} notified; patient told what happens next."
            ),
            owner=next_owner,
            new_stage=next_stage,
        )
    else:
        action = ExecutedAction(
            action_type="discharge_checklist",
            message=(
                f"Discharge checklist sent to {owner}: instructions, follow-up owner, "
                "transport, patient understanding."
            ),
            owner=owner,
        )

    store.add_event(
        case.id,
        "system",
        "action_executed",
        action.message,
        {"guidance_event_id": guidance_event_id, "approved_by": approver, **action.to_dict()},
    )
    return action
