import json
import unittest
from unittest.mock import patch

import httpx

from polaris_guidance.contracts import AgentRole, PatientBrief
from polaris_guidance.hermes_client import HermesClient, _extract_json


class HermesResponseTests(unittest.TestCase):
    def test_extracts_guidance_from_responses_api_shape(self):
        expected = {
            "summary": "Records are delayed.",
            "next_action": "Ask registration for an ETA.",
            "owner": "registration team",
            "rationale": "The barrier is unresolved.",
        }
        payload = {
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": json.dumps(expected)}],
                }
            ]
        }

        self.assertEqual(_extract_json(payload), expected)

    def test_rejects_non_json_model_output(self):
        payload = {
            "output": [{"type": "message", "content": [{"type": "output_text", "text": "hello"}]}]
        }

        with self.assertRaises(json.JSONDecodeError):
            _extract_json(payload)

    def test_rejects_missing_output_list(self):
        with self.assertRaisesRegex(ValueError, "output list"):
            _extract_json({})

    def test_extracts_fenced_json(self):
        payload = {
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": '```json\n{"a": 1}\n```'}],
                }
            ]
        }
        self.assertEqual(_extract_json(payload), {"a": 1})


class FakeAsyncClient:
    last_payload = None

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def post(self, url, *, json, headers):
        FakeAsyncClient.last_payload = json
        request = httpx.Request("POST", url)
        body = {
            "patient_need": "A clear update",
            "unanswered_questions": [],
            "communication_note": "Use plain language",
        }
        return httpx.Response(
            200,
            request=request,
            json={
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": json_module.dumps(body)}],
                    }
                ]
            },
        )


json_module = json


class HermesClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_requires_api_key(self):
        client = HermesClient("http://localhost/v1", "", "test-model")
        with self.assertRaisesRegex(RuntimeError, "not configured"):
            await client.complete_json(
                role=AgentRole.PATIENT_ADVOCATE,
                instructions="Summarize",
                payload={},
                output_type=PatientBrief,
            )

    async def test_validates_typed_response_and_disables_reasoning(self):
        client = HermesClient("http://localhost/v1", "key", "test-model")
        with patch("polaris_guidance.hermes_client.httpx.AsyncClient", FakeAsyncClient):
            result = await client.complete_json(
                role=AgentRole.PATIENT_ADVOCATE,
                instructions="Summarize",
                payload={"case": "demo"},
                output_type=PatientBrief,
            )
        self.assertEqual(result.patient_need, "A clear update")
        self.assertEqual(
            FakeAsyncClient.last_payload["model_options"],
            {"reasoning": {"enabled": False}},
        )

    async def test_openai_provider_uses_json_mode_without_hermes_options(self):
        client = HermesClient("https://api.openai.com/v1", "key", "gpt-4.1-mini", provider="openai")
        with patch("polaris_guidance.hermes_client.httpx.AsyncClient", FakeAsyncClient):
            await client.complete_json(
                role=AgentRole.PATIENT_ADVOCATE,
                instructions="Summarize",
                payload={"case": "demo"},
                output_type=PatientBrief,
            )
        self.assertNotIn("model_options", FakeAsyncClient.last_payload)
        self.assertEqual(FakeAsyncClient.last_payload["text"], {"format": {"type": "json_object"}})


if __name__ == "__main__":
    unittest.main()
