from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

STAGES = (
    "arrival",
    "registration",
    "triage",
    "clinical_review",
    "diagnostics",
    "treatment",
    "discharge",
)

ALLOWED_ACTORS = {"patient", "nurse", "doctor", "diagnostics", "admin", "system"}
ALLOWED_EVENT_TYPES = {
    "note",
    "stage_changed",
    "barrier_reported",
    "barrier_resolved",
    "guidance_proposed",
    "guidance_approved",
    "guidance_dismissed",
}


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class Case:
    id: str
    display_name: str
    reason: str
    stage: str
    urgency: str
    consent_to_coordinate: bool
    language: str
    created_at: str
    updated_at: str
    target_minutes: int


@dataclass(frozen=True)
class Event:
    id: str
    case_id: str
    actor: str
    event_type: str
    message: str
    created_at: str
    metadata: dict[str, object]


class CaseStore:
    """Small auditable store for the hackathon demo; no production PHI guarantees."""

    def __init__(self, path: str | Path):
        self.path = str(path)
        self._initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS cases (
                    id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    urgency TEXT NOT NULL,
                    consent_to_coordinate INTEGER NOT NULL,
                    language TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    target_minutes INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL REFERENCES cases(id),
                    actor TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    metadata TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_events_case_time
                    ON events(case_id, created_at);
                """
            )

    def create_case(
        self,
        *,
        display_name: str,
        reason: str,
        urgency: str,
        consent_to_coordinate: bool,
        language: str = "English",
        target_minutes: int = 45,
    ) -> Case:
        now = utc_now()
        case = Case(
            id=f"PG-{uuid.uuid4().hex[:8].upper()}",
            display_name=display_name.strip(),
            reason=reason.strip(),
            stage="arrival",
            urgency=urgency,
            consent_to_coordinate=consent_to_coordinate,
            language=language.strip() or "English",
            created_at=now,
            updated_at=now,
            target_minutes=target_minutes,
        )
        with self._connection() as db:
            db.execute(
                "INSERT INTO cases VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    case.id,
                    case.display_name,
                    case.reason,
                    case.stage,
                    case.urgency,
                    int(case.consent_to_coordinate),
                    case.language,
                    case.created_at,
                    case.updated_at,
                    case.target_minutes,
                ),
            )
        self.add_event(case.id, "patient", "note", "Patient journey opened.")
        return case

    def list_cases(self) -> list[Case]:
        with self._connection() as db:
            rows = db.execute("SELECT * FROM cases ORDER BY updated_at DESC").fetchall()
        return [self._case_from_row(row) for row in rows]

    def get_case(self, case_id: str) -> Case | None:
        with self._connection() as db:
            row = db.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
        return self._case_from_row(row) if row else None

    def update_stage(self, case_id: str, stage: str, actor: str) -> Case:
        if stage not in STAGES:
            raise ValueError(f"Unknown stage: {stage}")
        case = self.require_case(case_id)
        if STAGES.index(stage) < STAGES.index(case.stage):
            raise ValueError("A patient journey cannot move backward without opening a new case.")
        now = utc_now()
        with self._connection() as db:
            db.execute(
                "UPDATE cases SET stage = ?, updated_at = ? WHERE id = ?",
                (stage, now, case_id),
            )
        self.add_event(
            case_id,
            actor,
            "stage_changed",
            f"Stage moved to {stage.replace('_', ' ')}.",
        )
        return self.require_case(case_id)

    def add_event(
        self,
        case_id: str,
        actor: str,
        event_type: str,
        message: str,
        metadata: dict[str, object] | None = None,
    ) -> Event:
        self.require_case(case_id)
        if actor not in ALLOWED_ACTORS:
            raise ValueError(f"Unknown actor: {actor}")
        if event_type not in ALLOWED_EVENT_TYPES:
            raise ValueError(f"Unknown event type: {event_type}")
        now = utc_now()
        event = Event(
            id=f"EV-{uuid.uuid4().hex[:10].upper()}",
            case_id=case_id,
            actor=actor,
            event_type=event_type,
            message=message.strip(),
            created_at=now,
            metadata=metadata or {},
        )
        with self._connection() as db:
            db.execute(
                "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    event.id,
                    event.case_id,
                    event.actor,
                    event.event_type,
                    event.message,
                    event.created_at,
                    json.dumps(event.metadata),
                ),
            )
            db.execute("UPDATE cases SET updated_at = ? WHERE id = ?", (now, case_id))
        return event

    def list_events(self, case_id: str) -> list[Event]:
        self.require_case(case_id)
        with self._connection() as db:
            rows = db.execute(
                "SELECT * FROM events WHERE case_id = ? ORDER BY created_at",
                (case_id,),
            ).fetchall()
        return [
            Event(
                id=row["id"],
                case_id=row["case_id"],
                actor=row["actor"],
                event_type=row["event_type"],
                message=row["message"],
                created_at=row["created_at"],
                metadata=json.loads(row["metadata"]),
            )
            for row in rows
        ]

    def require_guidance(self, case_id: str, event_id: str) -> Event:
        events = self.list_events(case_id)
        guidance = next(
            (
                event
                for event in events
                if event.id == event_id and event.event_type == "guidance_proposed"
            ),
            None,
        )
        if guidance is None:
            raise ValueError("The referenced guidance proposal does not exist for this case.")
        if any(
            event.event_type in {"guidance_approved", "guidance_dismissed"}
            and event.metadata.get("guidance_event_id") == event_id
            for event in events
        ):
            raise ValueError("The referenced guidance proposal already has a decision.")
        return guidance

    def require_case(self, case_id: str) -> Case:
        case = self.get_case(case_id)
        if not case:
            raise KeyError(case_id)
        return case

    @staticmethod
    def _case_from_row(row: sqlite3.Row) -> Case:
        values = dict(row)
        values["consent_to_coordinate"] = bool(values["consent_to_coordinate"])
        return Case(**values)

    def case_snapshot(self, case_id: str) -> dict[str, object]:
        return {
            "case": asdict(self.require_case(case_id)),
            "events": [asdict(event) for event in self.list_events(case_id)],
        }
