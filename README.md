# Polaris Guidance Agent

[![Quality](https://github.com/gowtham66867/Polaris/actions/workflows/quality.yml/badge.svg)](https://github.com/gowtham66867/Polaris/actions/workflows/quality.yml)

MIT licensed. See [LICENSE](LICENSE).

Polaris is a hospital-agnostic patient guidance and operations coordination layer. It gives a
patient and their hospital team one shared view of the journey, identifies avoidable delays,
and drafts the next coordination action. It does **not** diagnose, recommend treatment, or
override clinical triage.

This repository is a Polaris hackathon MVP built to use the local
[Hermes Agent API server](https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server)
with a Claude model selected through Hermes.

**Live demo:** [Polaris on Google Cloud Run](https://polaris-guidance-mb3wwhqg6q-el.a.run.app)

**Independent AWS demo:**
[Polaris on Amazon EC2](http://ec2-65-0-108-126.ap-south-1.compute.amazonaws.com)

The public demo uses synthetic data, ephemeral SQLite storage, and the deterministic safety
engine. It does not contain cloud-hosted Hermes/Claude credentials and is not approved for PHI.

## Submission writeup

Hospital visits often stall because every handoff creates another queue and no one owns the next
operational step. Polaris gives the patient one coordination agent while each hospital keeps an
isolated orchestrator. The patient agent carries intent, accessibility needs, readiness, and schedule
context. A hospital receives only the fields needed to prepare admission, pharmacy, physiotherapy,
billing, transport, or another named service.

The agent reaches operational coordination: it identifies an owner, detects barriers, proposes one
allowlisted action, and records the approved outcome. It stops before clinical judgment. Emergency
language routes directly to human staff; clinical questions go only to licensed clinicians. Polaris
never diagnoses, interprets results, recommends treatment, changes priority, or invents capacity.

The architecture combines deterministic safety gates with a three-role harness: patient advocate,
operations coordinator, and independent safety reviewer. Strict schemas and a local policy engine
validate every model draft. Provider, parsing, policy, or reviewer failure falls closed to
deterministic guidance. A worker must approve an action before the synthetic workflow advances, and
the timeline preserves the decision and execution result.

TrueForge provides the judge-facing agent harness. The repository includes an importable Polaris
skill and saved-agent instructions. TrueForge runs the live agent loop, persists the demonstration
session, exposes the model trace, and pauses at the human checkpoint. The deployed FastAPI app keeps
its own matching safety harness so the demo remains available if the local TrueForge session is
offline.

Real today: the public app, multi-hospital isolation, consent-scoped disclosure log, conflict
handling, specialist fallback, audit events, 66 tests, 92% branch-aware coverage, and 8/8 safety
evaluations. Mocked: patients, hospitals, queues, connectors, and the 41-minute counterfactual saving.
Known limits include no production identity provider, PHI controls, certified clinical governance,
write-enabled EHR integration, or hospital outcome study.

## The problem

A patient's wait is often made of invisible handoffs: registration is waiting for records,
diagnostics is waiting for transport, or the patient simply does not know who owns the next
step. Hospital systems differ, but these coordination failures share the same shape.

Polaris creates a thin, vendor-neutral journey layer:

```text
Patient + family ─┐
                  ├── Shared journey timeline ── Rules + Hermes/Claude ── Draft next action
Hospital teams ───┘                                      │
                                                         └── Human approval + audit event
```

## What works now

- Synthetic patient journeys across arrival, registration, triage, clinical review,
  diagnostics, treatment, and discharge
- Shared event timeline for patients and hospital roles
- Wait targets and visible bottleneck flags
- Deterministic guidance that continues to work when Hermes is offline
- Three-role Hermes + Claude harness through `/v1/responses`: patient advocate, operations
  coordinator, and independent safety reviewer
- Strict role-specific output schemas, prompt-injection handling, fail-closed fallback, and
  persistent run traces with model/timing/policy metadata
- Emergency-language escalation without diagnosis or treatment advice
- Required staff approval/dismissal and an immutable decision event
- Duplicate-decision prevention, optional strict API-key RBAC, security headers, and request IDs
- Read-only FHIR R4 adapter boundary plus a synthetic hospital adapter
- Canonical ownership/dependency graph with stage owners, barriers, expected durations, and
  journey-risk forecasting
- Two portability demonstrations: Northstar Medical Center over FHIR R4 and Lakeside Community
  Hospital over HL7 v2, both mapped into the same journey model
- Closed-loop barrier resolution and handoff completion
- A patient-owned care-network layer spanning multiple hospital contexts without combining their
  records: deterministic need routing, explicit consent, minimum-necessary disclosure, and an
  expiring sharing log
- Cross-hospital appointment-conflict detection and private resolution that reveals only the busy
  window—not the other hospital or visit details
- Hospital-scoped specialist agents with named backup routing, readiness/pre-positioning,
  just-in-time patient notifications, and surge-to-human escalation
- Deterministic emergency and clinical-question gates that run before any model; clinical questions
  are sent only to a consenting patient's human nursing team
- A visible prompt-injection challenge that proves timeline content cannot redefine the agent
- A versioned 12-scenario counterfactual simulation comparing manual routing with Polaris;
  results are explicitly labeled synthetic rather than presented as clinical evidence
- Local SQLite persistence and a responsive demo dashboard

## Run the demo

### TrueForge judge harness

Run TrueForge locally, configure a model in **Settings → Models**, import
`trueforge/polaris-care-coordinator` from this public repository under **Settings → Skills**, and
create the saved agent from [the supplied instructions](trueforge/AGENT_INSTRUCTIONS.md):

```bash
npx @truefoundry/trueforge@latest
```

Open [http://localhost:8790](http://localhost:8790). Local mode has no login by default, so keep it
on localhost. The submission video must show at least 30 seconds of this TrueForge flow.

### 1. Start Hermes with a model

Configure a provider and select a Claude model:

```bash
hermes model
```

Polaris targets `anthropic/claude-opus-5`, corresponding to Anthropic's verified API model
`claude-opus-5`. Anthropic does not currently publish a `Claude Opus 5.5` model identifier,
so Polaris does not invent an unsupported slug.

Enable the API server in the active Hermes profile's `.env`:

```bash
API_SERVER_ENABLED=true
API_SERVER_KEY=change-me-local-dev
```

Then start it:

```bash
hermes gateway
```

### 2. Start Polaris

```bash
cd "/Users/gowtham/Downloads/AIAgent/Polaris"
uv sync --extra test
cp .env.example .env
set -a; . ./.env; set +a
uv run uvicorn polaris_guidance.app:app --reload --port 8080
```

Open [http://127.0.0.1:8080](http://127.0.0.1:8080). API docs are at
[http://127.0.0.1:8080/docs](http://127.0.0.1:8080/docs).

Without a Hermes key, the complete workflow still runs using deterministic, safety-checked
guidance. This makes the demo resilient on stage.

## Safety boundary

Polaris is a workflow coordination prototype, not a medical device.

- It never diagnoses, interprets results, recommends treatment, or changes clinical priority.
- Emergency language bypasses normal workflow guidance and directs immediate escalation to
  the hospital's emergency/triage process.
- No external action is executed automatically; a staff member approves or dismisses drafts.
  Approval can advance the synthetic journey or open a named escalation, with an audit event.
- The UI says to use synthetic data. Do not enter real protected health information in this MVP.
- A production deployment requires authentication, role-based access, encryption, retention
  rules, consent withdrawal, threat modeling, clinical safety review, and applicable regulatory
  and privacy compliance.

## Hospital-agnostic integration plan

The MVP owns a minimal canonical case/event model. The patient agent is the only component with
cross-hospital schedule context; each hospital receives a scoped request and retains an isolated
operational view. Real hospitals connect through adapters:

1. FHIR R4/R5 for Patient, Encounter, Appointment, Task, ServiceRequest, and Communication.
2. SMART on FHIR for scoped staff/patient authorization.
3. HL7 v2 adapters where FHIR is unavailable.
4. Messaging/EHR write operations remain draft-only until policy and role checks approve them.

The next hackathon milestone is a `HospitalAdapter` interface with a demo adapter plus one
read-only FHIR sandbox integration. That keeps the guidance engine stable across vendors.

## Test

```bash
make quality
```

The quality gate runs Ruff lint/format checks, strict mypy, branch-aware coverage with an 80%
minimum, the complete test suite, and adversarial safety evaluations. The current verified
baseline is 66 tests, 92% coverage, and 8/8 safety scenarios.

See [Architecture](docs/ARCHITECTURE.md) and [Security](SECURITY.md) for system boundaries.
The hackathon package is documented in the [submission brief](docs/SUBMISSION.md), and the
[final presentation](docs/Polaris-Agents-That-Act-Submission.pptx) is versioned with the code.

Contributors should follow [CONTRIBUTING.md](CONTRIBUTING.md); the same `make quality` command is
the required local and GitHub Actions gate.

## Separate AWS deployment

The existing Cloud Run demo can remain online while a second, independent copy runs on one small
Amazon EC2 instance. This path is compatible with AWS's no-overage Free account plan. The script
uses Mumbai by default, a `t3.micro` instance with standard CPU credits, one encrypted 8 GB volume,
no autoscaling, and a security group that exposes only HTTP. Amazon Linux installs Docker and
builds the exact Git revision supplied by the script.

Prerequisites are Git, AWS CLI authentication, and permission to manage EC2 resources.
Authenticate without placing long-lived credentials in this repository:

```bash
aws login
AWS_REGION=ap-south-1 ./scripts/deploy_aws_ec2.sh
```

### Live agents on AWS (Gemini or OpenAI) and in-place updates

Without a model key the agents fail closed to the deterministic policy engine. To run the live
three-agent pipeline on AWS, store a Gemini key as SecureString `/polaris/gemini_api_key` (or the
hackathon OpenAI key as `/polaris/openai_api_key`) in Systems Manager Parameter Store
(ap-south-1), then redeploy in place
(the public URL does not change):

```bash
AWS_REGION=ap-south-1 ./scripts/update_aws_ec2.sh
```

The key is read on the instance at container start; it is never committed or placed in user
data. Locally, Hermes stays the preferred gateway when `POLARIS_HERMES_API_KEY` is set;
otherwise `GEMINI_API_KEY` selects Gemini (`POLARIS_GEMINI_MODEL`, default `gemini-2.5-flash`),
then `OPENAI_API_KEY` selects OpenAI (`POLARIS_OPENAI_MODEL`, default `gpt-4.1-mini`).
Approving guidance now executes the coordination action (handoff, owner escalation, status
request, or discharge checklist) and records it on the shared timeline.

The AWS deployment uses the same synthetic demo mode and safety fallback as Cloud Run. It does
not include model credentials or permit real patient data. Connect a hosted Hermes or TrueForge
service through a secret-managed integration rather than committing provider keys.

## Contribution credit

The multi-hospital patient-agent concepts in the v0.3 care-network layer were adapted from
SIJO JOHN's `sijo` branch (`6460f0a`): hospital isolation, minimum-necessary disclosure,
cross-hospital conflict handling, readiness/pre-positioning, specialist failover, and surge
escalation. The implementation was rewritten against Polaris's existing FastAPI contracts so the
deployed application, safety harness, and audit model remain intact.
