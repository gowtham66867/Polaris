from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AgentRole(StrEnum):
    PATIENT_ADVOCATE = "patient_advocate"
    OPERATIONS_COORDINATOR = "operations_coordinator"
    SAFETY_REVIEWER = "safety_reviewer"


class PatientBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patient_need: str = Field(min_length=1, max_length=400)
    unanswered_questions: list[str] = Field(default_factory=list, max_length=5)
    communication_note: str = Field(min_length=1, max_length=240)


class CoordinationDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=400)
    next_action: str = Field(min_length=1, max_length=500)
    owner: str = Field(min_length=1, max_length=80)
    rationale: str = Field(min_length=1, max_length=400)


class SafetyVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approved: bool
    concerns: list[str] = Field(default_factory=list, max_length=8)
    rewritten_action: str | None = Field(default=None, max_length=500)


class AgentStep(BaseModel):
    role: AgentRole
    status: Literal["completed", "blocked", "fallback"]
    duration_ms: int = Field(ge=0)
    output: dict[str, Any]


class AgentRun(BaseModel):
    run_id: str
    case_id: str
    status: Literal["completed", "blocked", "fallback"]
    model: str
    steps: list[AgentStep]
    policy_checks: list[str]
    guidance: dict[str, Any]
