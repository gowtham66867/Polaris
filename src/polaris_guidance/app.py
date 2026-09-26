from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import cast

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.base import RequestResponseEndpoint

from .domain import STAGES, Case, CaseStore
from .engine import elapsed_minutes
from .harness import GuidanceOrchestrator
from .hermes_client import HermesClient
from .security import Principal, require_roles

PACKAGE_DIR = Path(__file__).parent
STATIC_DIR = PACKAGE_DIR / "static"
DB_PATH = os.environ.get("POLARIS_DB_PATH", "polaris-guidance.db")


class CaseCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)
    reason: str = Field(min_length=2, max_length=500)
    urgency: str = Field(default="routine", pattern="^(routine|urgent)$")
    consent_to_coordinate: bool
    language: str = Field(default="English", max_length=40)
    target_minutes: int = Field(default=45, ge=5, le=360)


class EventCreate(BaseModel):
    actor: str
    event_type: str
    message: str = Field(min_length=1, max_length=1000)
    metadata: dict[str, object] = Field(default_factory=dict)


class StageUpdate(BaseModel):
    stage: str
    actor: str


class Decision(BaseModel):
    guidance_event_id: str
    actor: str
    approved: bool


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.store = CaseStore(DB_PATH)
    if not app.state.store.list_cases():
        _seed_demo(app.state.store)
    yield


app = FastAPI(
    title="Polaris Guidance Agent",
    version="0.1.0",
    description="Patient-advocacy and hospital-operations coordination; not a medical device.",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def security_headers(request: Request, call_next: RequestResponseEndpoint) -> Response:
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Request-ID"] = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    return response


@app.get("/", include_in_schema=False)
def dashboard() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "polaris-guidance"}


@app.get("/api/cases")
def list_cases() -> list[dict[str, object]]:
    return [_case_view(case) for case in app.state.store.list_cases()]


@app.post("/api/cases", status_code=201)
def create_case(
    body: CaseCreate,
    _principal: Principal = Depends(require_roles("patient", "nurse", "doctor")),
) -> dict[str, object]:
    if not body.consent_to_coordinate:
        raise HTTPException(400, "Consent is required before the agent coordinates a case.")
    case = app.state.store.create_case(**body.model_dump())
    return _case_view(case)


@app.get("/api/cases/{case_id}")
def get_case(case_id: str) -> dict[str, object]:
    try:
        snapshot = cast(dict[str, object], app.state.store.case_snapshot(case_id))
    except KeyError:
        raise HTTPException(404, "Case not found") from None
    snapshot["case"] = _case_view(app.state.store.require_case(case_id))
    return snapshot


@app.post("/api/cases/{case_id}/events", status_code=201)
def add_event(
    case_id: str,
    body: EventCreate,
    _principal: Principal = Depends(require_roles("patient", "nurse", "doctor", "diagnostics")),
) -> dict[str, object]:
    try:
        event = app.state.store.add_event(case_id, **body.model_dump())
    except KeyError:
        raise HTTPException(404, "Case not found") from None
    except ValueError as error:
        raise HTTPException(400, str(error)) from None
    return cast(dict[str, object], asdict(event))


@app.post("/api/cases/{case_id}/stage")
def update_stage(
    case_id: str,
    body: StageUpdate,
    _principal: Principal = Depends(require_roles("nurse", "doctor", "diagnostics")),
) -> dict[str, object]:
    try:
        case = app.state.store.update_stage(case_id, body.stage, body.actor)
    except KeyError:
        raise HTTPException(404, "Case not found") from None
    except ValueError as error:
        raise HTTPException(400, str(error)) from None
    return _case_view(case)


@app.post("/api/cases/{case_id}/guide")
async def guide(
    case_id: str,
    _principal: Principal = Depends(require_roles("nurse", "doctor")),
) -> dict[str, object]:
    try:
        case = app.state.store.require_case(case_id)
        events = app.state.store.list_events(case_id)
    except KeyError:
        raise HTTPException(404, "Case not found") from None

    api_key = os.environ.get("POLARIS_HERMES_API_KEY", "")
    client = (
        HermesClient(
            base_url=os.environ.get("POLARIS_HERMES_API_URL", "http://127.0.0.1:8642/v1"),
            api_key=api_key,
            model=os.environ.get("POLARIS_HERMES_MODEL", "anthropic/claude-sonnet-5"),
        )
        if api_key
        else None
    )
    run = await GuidanceOrchestrator(client).run(case, events)
    guidance = run.guidance
    warning = (
        "Hermes unavailable; showing safety-checked workflow guidance."
        if run.status == "fallback"
        else None
    )

    event = app.state.store.add_event(
        case_id,
        "system",
        "guidance_proposed",
        str(guidance["next_action"]),
        {"run": run.model_dump(), "warning": warning},
    )
    return {
        "event_id": event.id,
        "run_id": run.run_id,
        "run_status": run.status,
        "steps": [step.model_dump() for step in run.steps],
        "policy_checks": run.policy_checks,
        "guidance": guidance,
        "warning": warning,
    }


@app.post("/api/cases/{case_id}/decision")
def decide(
    case_id: str,
    body: Decision,
    _principal: Principal = Depends(require_roles("nurse", "doctor")),
) -> dict[str, object]:
    event_type = "guidance_approved" if body.approved else "guidance_dismissed"
    label = "approved" if body.approved else "dismissed"
    try:
        app.state.store.require_guidance(case_id, body.guidance_event_id)
        event = app.state.store.add_event(
            case_id,
            body.actor,
            event_type,
            f"Guidance {body.guidance_event_id} {label} by {body.actor}.",
            {"guidance_event_id": body.guidance_event_id},
        )
    except (KeyError, ValueError) as error:
        raise HTTPException(400, str(error)) from None
    return asdict(event)


@app.get("/api/metrics")
def metrics() -> dict[str, object]:
    cases = app.state.store.list_cases()
    waits = [elapsed_minutes(case) for case in cases]
    by_stage = {stage: sum(case.stage == stage for case in cases) for stage in STAGES}
    return {
        "active_cases": len(cases),
        "average_wait_minutes": round(sum(waits) / len(waits), 1) if waits else 0,
        "over_target": sum(
            wait > case.target_minutes for wait, case in zip(waits, cases, strict=True)
        ),
        "by_stage": by_stage,
    }


def _case_view(case: Case) -> dict[str, object]:
    view = cast(dict[str, object], asdict(case))
    elapsed = elapsed_minutes(case)
    view["elapsed_minutes"] = elapsed
    view["over_target"] = elapsed > case.target_minutes
    return view


def _seed_demo(store: CaseStore) -> None:
    first = store.create_case(
        display_name="Maya (demo)",
        reason="Persistent abdominal discomfort; awaiting clinician review.",
        urgency="routine",
        consent_to_coordinate=True,
        language="English",
        target_minutes=45,
    )
    store.update_stage(first.id, "registration", "admin")
    store.update_stage(first.id, "triage", "nurse")
    store.add_event(first.id, "nurse", "barrier_reported", "Previous records have not arrived.")

    second = store.create_case(
        display_name="Arun (demo)",
        reason="Scheduled imaging appointment.",
        urgency="routine",
        consent_to_coordinate=True,
        language="Tamil",
        target_minutes=30,
    )
    store.update_stage(second.id, "registration", "admin")
    store.update_stage(second.id, "triage", "nurse")
    store.update_stage(second.id, "clinical_review", "doctor")
    store.update_stage(second.id, "diagnostics", "diagnostics")
