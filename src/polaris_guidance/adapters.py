from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class HospitalContext:
    hospital_id: str
    encounter_id: str
    tasks: list[dict[str, Any]]
    source: str


class HospitalAdapter(ABC):
    """Read-only boundary between Polaris and a hospital system."""

    @abstractmethod
    async def encounter_context(self, encounter_id: str) -> HospitalContext:
        raise NotImplementedError


class DemoHospitalAdapter(HospitalAdapter):
    async def encounter_context(self, encounter_id: str) -> HospitalContext:
        return HospitalContext(
            hospital_id="demo-general",
            encounter_id=encounter_id,
            tasks=[],
            source="synthetic",
        )


class ReadOnlyFHIRAdapter(HospitalAdapter):
    """Minimal FHIR R4 adapter. It deliberately exposes no write operation."""

    def __init__(self, base_url: str, bearer_token: str, timeout: float = 15):
        if not base_url.startswith("https://"):
            raise ValueError("FHIR base URL must use HTTPS.")
        self.base_url = base_url.rstrip("/")
        self.bearer_token = bearer_token
        self.timeout = timeout

    async def encounter_context(self, encounter_id: str) -> HospitalContext:
        headers = {
            "Authorization": f"Bearer {self.bearer_token}",
            "Accept": "application/fhir+json",
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            encounter_response = await client.get(
                f"{self.base_url}/Encounter/{encounter_id}", headers=headers
            )
            encounter_response.raise_for_status()
            task_response = await client.get(
                f"{self.base_url}/Task",
                params={"encounter": encounter_id, "_count": "50"},
                headers=headers,
            )
            task_response.raise_for_status()
        task_bundle = task_response.json()
        tasks = [entry.get("resource", {}) for entry in task_bundle.get("entry", [])]
        return HospitalContext(
            hospital_id=self.base_url,
            encounter_id=encounter_id,
            tasks=tasks,
            source="fhir-r4",
        )
