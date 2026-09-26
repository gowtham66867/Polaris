from __future__ import annotations

import re
from dataclasses import dataclass

from .contracts import CoordinationDraft

CLINICAL_PATTERNS = (
    r"\bdiagnos(?:e|is|ed)\b",
    r"\bprescri(?:be|ption)\b",
    r"\b(?:take|administer|increase|decrease)\s+\d+(?:\.\d+)?\s*(?:mg|ml|mcg)\b",
    r"\bskip (?:the )?(?:triage|queue)\b",
    r"\bdiscontinue (?:the )?medication\b",
)

INJECTION_PATTERNS = (
    r"ignore (?:all |the )?(?:previous|prior|system) instructions",
    r"reveal (?:the )?(?:system prompt|instructions|secret|api key)",
    r"act as (?:a )?(?:doctor|clinician)",
    r"developer message",
)

ALLOWED_OWNERS = {
    "front desk",
    "registration team",
    "triage nurse",
    "clinical team",
    "diagnostics team",
    "care team",
    "discharge coordinator",
}


@dataclass(frozen=True)
class PolicyResult:
    allowed: bool
    checks: list[str]
    concerns: list[str]


def sanitize_untrusted_text(value: str, limit: int = 1000) -> str:
    value = " ".join(value.replace("\x00", " ").split())
    return value[:limit]


def detect_prompt_injection(text: str) -> bool:
    lowered = text.casefold()
    return any(re.search(pattern, lowered) for pattern in INJECTION_PATTERNS)


def validate_draft(draft: CoordinationDraft) -> PolicyResult:
    combined = f"{draft.summary} {draft.next_action} {draft.rationale}".casefold()
    concerns: list[str] = []
    checks = ["non_clinical_scope", "known_owner", "no_autonomous_execution", "bounded_output"]
    if any(re.search(pattern, combined) for pattern in CLINICAL_PATTERNS):
        concerns.append("Draft crosses the non-clinical coordination boundary.")
    if draft.owner.casefold() not in ALLOWED_OWNERS:
        concerns.append("Draft assigns an unknown or unauthorized owner.")
    return PolicyResult(allowed=not concerns, checks=checks, concerns=concerns)
