"""Hospital-network coordination primitives adapted from Sijo's prototype.

The patient agent owns cross-hospital context. Each hospital receives only the
minimum fields needed for one operational request, and clinical/emergency text
is handled by deterministic gates before any model can see it.
"""

from __future__ import annotations

import re
import uuid
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from typing import Any, Literal

SafetyLevel = Literal["emergency", "clinical", "ok"]

EMERGENCY_PATTERNS = (
    re.compile(r"chest (pain|tightness|pressure)", re.I),
    re.compile(r"(can'?t|cannot|trouble|difficulty|hard to) breath", re.I),
    re.compile(r"\b(stroke|seizure|overdose|emergency)\b", re.I),
    re.compile(r"(unconscious|passed out|collapsed|heavy bleeding)", re.I),
    re.compile(r"(suicid|kill myself|end my life|self[- ]?harm)", re.I),
)
CLINICAL_PATTERNS = (
    re.compile(r"\b(symptom|dose|dosage|side[- ]?effect|diagnos|treatment)\b", re.I),
    re.compile(r"should i (take|stop|eat|drink|worry|exercise)", re.I),
    re.compile(r"(pain|fever|rash|dizz|nause|bleed|swollen)", re.I),
    re.compile(r"what do(es)? .* (result|reading|level)s? mean", re.I),
)

INTENT_RULES = (
    ("check_in", re.compile(r"check (me )?in|i('?m| am) here|arrived", re.I)),
    ("reschedule", re.compile(r"reschedul|move my|different time|later slot", re.I)),
    ("payment_plan", re.compile(r"payment plan|instal+ment|can'?t afford", re.I)),
    ("bill_question", re.compile(r"\b(bill|invoice|charge|insurance|balance)\b", re.I)),
    ("accessibility", re.compile(r"wheelchair|interpreter|translat|can'?t walk", re.I)),
    ("prescription", re.compile(r"prescription|medicine ready|pharmacy|pick ?up", re.I)),
    ("results", re.compile(r"results?|lab|blood test", re.I)),
    ("appointment", re.compile(r"appointment|what time|where do i go|what'?s next", re.I)),
    ("human", re.compile(r"human|real person|speak to|talk to", re.I)),
)

INTENT_SPECIALIST = {
    "check_in": "scheduling",
    "reschedule": "scheduling",
    "appointment": "scheduling",
    "payment_plan": "billing",
    "bill_question": "billing",
    "accessibility": "accessibility",
    "prescription": "pharmacy",
    "results": "diagnostics",
    "clinical_question": "nursing",
    "human": "nursing",
    "other": "orchestrator",
}

DISCLOSURE_SCOPES = {
    "scheduling": {"appointment_id", "preferred_window", "busy_window", "zone"},
    "billing": {"invoice_id", "insurance", "payment_preference"},
    "accessibility": {"accessibility", "zone", "eta_minutes"},
    "pharmacy": {"prescription_ids", "allergies"},
    "diagnostics": {"order_ids"},
    "nursing": {"question", "allergies"},
    "orchestrator": {"summary", "zone", "eta_minutes"},
}

HOSPITAL_SEED: dict[str, dict[str, Any]] = {
    "stmarys": {
        "name": "St. Mary's Medical Center",
        "standard": "FHIR R4",
        "specialists": {
            "scheduling": {"available": True, "backup": "operations desk"},
            "billing": {"available": True, "backup": "patient services"},
            "accessibility": {"available": True, "backup": "campus concierge"},
            "pharmacy": {"available": True, "backup": "pharmacy desk"},
            "diagnostics": {"available": True, "backup": "care team"},
            "nursing": {"available": True, "backup": "charge nurse"},
            "orchestrator": {"available": True, "backup": "operations lead"},
        },
        "surges": {},
        "readiness": {},
        "human_escalations": 0,
    },
    "riverside": {
        "name": "Riverside General Hospital",
        "standard": "HL7 v2",
        "specialists": {
            "scheduling": {"available": True, "backup": "front desk"},
            "billing": {"available": True, "backup": "patient accounts"},
            "accessibility": {"available": True, "backup": "visitor services"},
            "pharmacy": {"available": True, "backup": "dispensary desk"},
            "diagnostics": {"available": True, "backup": "care team"},
            "nursing": {"available": True, "backup": "charge nurse"},
            "orchestrator": {"available": True, "backup": "operations lead"},
        },
        "surges": {},
        "readiness": {},
        "human_escalations": 0,
    },
}


@dataclass(frozen=True)
class SharingRecord:
    id: str
    patient_id: str
    hospital_id: str
    recipient: str
    purpose: str
    fields: list[str]
    created_at: str
    expires_at: str


def _now() -> datetime:
    return datetime.now(UTC)


def safety_level(text: str) -> SafetyLevel:
    if any(pattern.search(text) for pattern in EMERGENCY_PATTERNS):
        return "emergency"
    if any(pattern.search(text) for pattern in CLINICAL_PATTERNS):
        return "clinical"
    return "ok"


def classify_intent(text: str) -> str:
    for intent, pattern in INTENT_RULES:
        if pattern.search(text):
            return intent
    return "other"


def minimize_payload(specialist: str, payload: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    allowed = DISCLOSURE_SCOPES.get(specialist, set())
    minimized = {
        key: value for key, value in payload.items() if key in allowed and value is not None
    }
    stripped = sorted(
        key for key, value in payload.items() if key not in allowed and value is not None
    )
    return minimized, stripped


class CareNetwork:
    """In-memory synthetic network used by the hackathon demonstration."""

    def __init__(self) -> None:
        self.hospitals: dict[str, dict[str, Any]] = deepcopy(HOSPITAL_SEED)
        self.sharing_records: list[SharingRecord] = []
        self.notifications: list[dict[str, Any]] = []
        self.appointments: dict[str, list[dict[str, Any]]] = {
            "demo-patient": [
                {
                    "id": "SM-APT-901",
                    "hospital_id": "stmarys",
                    "department": "diagnostics",
                    "starts_at": "2026-09-27T10:00:00+05:30",
                    "ends_at": "2026-09-27T10:45:00+05:30",
                },
                {
                    "id": "RV-APT-551",
                    "hospital_id": "riverside",
                    "department": "physiotherapy",
                    "starts_at": "2026-09-27T10:30:00+05:30",
                    "ends_at": "2026-09-27T11:15:00+05:30",
                },
            ]
        }

    def snapshot(self, patient_id: str = "demo-patient") -> dict[str, Any]:
        conflicts = self.conflicts(patient_id)
        return {
            "hospitals": [self.hospital_view(hospital_id) for hospital_id in self.hospitals],
            "open_conflicts": conflicts,
            "sharing_log_count": len(self.sharing_records),
            "notifications": self.notifications[-8:],
            "privacy_boundary": "Cross-hospital context remains patient-owned.",
        }

    def hospital_view(self, hospital_id: str) -> dict[str, Any]:
        hospital = self._hospital(hospital_id)
        specialists = hospital["specialists"]
        return {
            "id": hospital_id,
            "name": hospital["name"],
            "standard": hospital["standard"],
            "specialists": {
                name: {"available": state["available"], "backup": state["backup"]}
                for name, state in specialists.items()
            },
            "surges": dict(hospital["surges"]),
            "human_escalations": hospital["human_escalations"],
            "readiness_count": len(hospital["readiness"]),
        }

    def route(
        self,
        *,
        patient_id: str,
        text: str,
        hospital_id: str | None,
        consent_to_share: bool,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        level = safety_level(text)
        if level == "emergency":
            target = hospital_id if hospital_id in self.hospitals else None
            if target:
                self.hospitals[target]["human_escalations"] += 1
            self._notify(
                patient_id, "emergency", "Call local emergency services now and alert nearby staff."
            )
            return {
                "safety": level,
                "status": "human_escalated",
                "hospital_id": target,
                "message": "Emergency routing bypassed every agent queue; no model was called.",
            }

        intent = "clinical_question" if level == "clinical" else classify_intent(text)
        if level == "clinical" and not consent_to_share:
            return {
                "safety": level,
                "status": "consent_required",
                "message": (
                    "This needs a clinician. May I send your question to the hospital nursing team?"
                ),
            }
        if hospital_id is None:
            return {
                "safety": level,
                "status": "hospital_required",
                "message": "Choose which connected hospital should receive this request.",
            }
        hospital = self._hospital(hospital_id)
        specialist = INTENT_SPECIALIST[intent]
        candidate = {**(payload or {})}
        if level == "clinical":
            candidate["question"] = text[:500]
        elif intent == "other":
            candidate["summary"] = text[:500]
        minimized, stripped = minimize_payload(specialist, candidate)
        if minimized and not consent_to_share:
            return {
                "safety": level,
                "status": "consent_required",
                "message": "Consent is required before sharing these fields with the hospital.",
                "fields": sorted(minimized),
            }

        specialist_state = hospital["specialists"][specialist]
        routed_to = specialist if specialist_state["available"] else specialist_state["backup"]
        status = "routed" if specialist_state["available"] else "backup_routed"
        if minimized:
            self._log_share(patient_id, hospital_id, str(routed_to), intent, sorted(minimized))
        if level == "clinical":
            hospital["human_escalations"] += 1
            status = "human_nurse_required"
        return {
            "safety": level,
            "intent": intent,
            "status": status,
            "hospital_id": hospital_id,
            "hospital": hospital["name"],
            "routed_to": routed_to,
            "shared_fields": sorted(minimized),
            "stripped_fields": stripped,
            "message": self._route_message(intent, status, str(routed_to)),
        }

    def conflicts(self, patient_id: str) -> list[dict[str, Any]]:
        appointments = sorted(
            self.appointments.get(patient_id, []), key=lambda item: item["starts_at"]
        )
        conflicts: list[dict[str, Any]] = []
        for first, second in pairwise(appointments):
            if first["hospital_id"] == second["hospital_id"]:
                continue
            if datetime.fromisoformat(second["starts_at"]) < datetime.fromisoformat(
                first["ends_at"]
            ):
                conflicts.append(
                    {
                        "id": f"{first['id']}::{second['id']}",
                        "first": dict(first),
                        "second": dict(second),
                        "privacy": (
                            "Only the busy window is disclosed to the hospital being rescheduled."
                        ),
                    }
                )
        return conflicts

    def resolve_conflict(self, patient_id: str, conflict_id: str) -> dict[str, Any]:
        conflict = next(
            (item for item in self.conflicts(patient_id) if item["id"] == conflict_id), None
        )
        if conflict is None:
            raise ValueError("Conflict does not exist or has already been resolved.")
        first = conflict["first"]
        second = conflict["second"]
        new_start = datetime.fromisoformat(first["ends_at"]) + timedelta(minutes=30)
        duration = datetime.fromisoformat(second["ends_at"]) - datetime.fromisoformat(
            second["starts_at"]
        )
        appointment = next(
            item for item in self.appointments[patient_id] if item["id"] == second["id"]
        )
        appointment["starts_at"] = new_start.isoformat()
        appointment["ends_at"] = (new_start + duration).isoformat()
        self._log_share(
            patient_id,
            str(second["hospital_id"]),
            "scheduling",
            "cross_hospital_conflict",
            ["appointment_id", "busy_window"],
        )
        message = (
            f"Moved {second['id']} after the conflicting window; "
            "the other hospital's identity and visit details were not shared."
        )
        self._notify(patient_id, "conflict_resolved", message)
        return {"status": "resolved", "appointment": dict(appointment), "message": message}

    def readiness(
        self, patient_id: str, hospital_id: str, zone: str, eta_minutes: int | None
    ) -> dict[str, Any]:
        if zone not in {"home", "en_route", "parking", "cafeteria", "lobby", "on_campus"}:
            raise ValueError("Unknown readiness zone.")
        hospital = self._hospital(hospital_id)
        hospital["readiness"][patient_id] = {"zone": zone, "eta_minutes": eta_minutes}
        fields = ["zone", *(["eta_minutes"] if eta_minutes is not None else [])]
        self._log_share(patient_id, hospital_id, "orchestrator", "readiness", fields)
        on_campus = zone in {"parking", "cafeteria", "lobby", "on_campus"}
        message = (
            "Departments pre-positioned; wait for a just-in-time proceed notification."
            if on_campus
            else "Arrival estimate shared; no clinical information was disclosed."
        )
        self._notify(patient_id, "readiness", message)
        return {"status": "prepositioned" if on_campus else "readiness_shared", "message": message}

    def set_specialist_availability(
        self, hospital_id: str, specialist: str, available: bool
    ) -> dict[str, Any]:
        hospital = self._hospital(hospital_id)
        if specialist not in hospital["specialists"]:
            raise ValueError("Unknown specialist agent.")
        hospital["specialists"][specialist]["available"] = available
        return {
            "hospital_id": hospital_id,
            "specialist": specialist,
            "available": available,
            "backup": hospital["specialists"][specialist]["backup"],
        }

    def set_surge(self, hospital_id: str, department: str, active: bool) -> dict[str, Any]:
        hospital = self._hospital(hospital_id)
        hospital["surges"][department] = active
        affected = sum(
            appointment["hospital_id"] == hospital_id and appointment["department"] == department
            for appointments in self.appointments.values()
            for appointment in appointments
        )
        if active:
            hospital["human_escalations"] += 1
            self.notifications.append(
                {
                    "patient_id": "affected-patients",
                    "kind": "delay",
                    "message": (
                        f"{department.title()} is experiencing delays; staff escalation opened."
                    ),
                }
            )
        return {
            "hospital_id": hospital_id,
            "department": department,
            "active": active,
            "affected": affected,
        }

    def sharing_log(self, patient_id: str) -> list[dict[str, Any]]:
        return [
            asdict(record) for record in self.sharing_records if record.patient_id == patient_id
        ]

    def _hospital(self, hospital_id: str) -> dict[str, Any]:
        hospital = self.hospitals.get(hospital_id)
        if hospital is None:
            raise KeyError(hospital_id)
        return hospital

    def _log_share(
        self,
        patient_id: str,
        hospital_id: str,
        recipient: str,
        purpose: str,
        fields: list[str],
    ) -> None:
        now = _now()
        self.sharing_records.append(
            SharingRecord(
                id=f"SH-{uuid.uuid4().hex[:10].upper()}",
                patient_id=patient_id,
                hospital_id=hospital_id,
                recipient=recipient,
                purpose=purpose,
                fields=fields,
                created_at=now.isoformat(),
                expires_at=(now + timedelta(hours=24)).isoformat(),
            )
        )

    def _notify(self, patient_id: str, kind: str, message: str) -> None:
        self.notifications.append({"patient_id": patient_id, "kind": kind, "message": message})

    @staticmethod
    def _route_message(intent: str, status: str, routed_to: str) -> str:
        if status == "backup_routed":
            label = intent.replace("_", " ")
            return f"The primary {label} agent is unavailable; routed to {routed_to}."
        if status == "human_nurse_required":
            return (
                "Your question was sent to a human nurse; the agent will not answer it clinically."
            )
        return f"Request accepted and routed to {routed_to}."
