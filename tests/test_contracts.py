import unittest

from pydantic import ValidationError

from polaris_guidance.contracts import CoordinationDraft, SafetyVerdict


class ContractTests(unittest.TestCase):
    def test_unknown_model_fields_are_rejected(self):
        with self.assertRaises(ValidationError):
            CoordinationDraft.model_validate(
                {
                    "summary": "ok",
                    "next_action": "Ask registration for an ETA.",
                    "owner": "registration team",
                    "rationale": "handoff",
                    "execute_now": True,
                }
            )

    def test_safety_verdict_bounds_concerns(self):
        with self.assertRaises(ValidationError):
            SafetyVerdict(approved=False, concerns=[str(i) for i in range(9)])
