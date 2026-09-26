import unittest
from unittest.mock import patch

import httpx

from polaris_guidance.adapters import DemoHospitalAdapter, ReadOnlyFHIRAdapter


class AdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_demo_adapter_returns_synthetic_context(self):
        context = await DemoHospitalAdapter().encounter_context("enc-1")
        self.assertEqual(context.encounter_id, "enc-1")
        self.assertEqual(context.source, "synthetic")

    def test_fhir_adapter_requires_tls(self):
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            ReadOnlyFHIRAdapter("http://hospital.test/fhir", "token")

    async def test_fhir_adapter_reads_encounter_and_tasks(self):
        class FakeClient:
            def __init__(self, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, traceback):
                return False

            async def get(self, url, **kwargs):
                request = httpx.Request("GET", url)
                if "/Task" in url:
                    return httpx.Response(
                        200,
                        request=request,
                        json={"entry": [{"resource": {"resourceType": "Task", "id": "t1"}}]},
                    )
                return httpx.Response(
                    200, request=request, json={"resourceType": "Encounter", "id": "enc-1"}
                )

        adapter = ReadOnlyFHIRAdapter("https://hospital.test/fhir", "token")
        with patch("polaris_guidance.adapters.httpx.AsyncClient", FakeClient):
            context = await adapter.encounter_context("enc-1")
        self.assertEqual(context.source, "fhir-r4")
        self.assertEqual(context.tasks[0]["id"], "t1")
