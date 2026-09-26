# Architecture

## Decision flow

1. The deterministic engine evaluates emergency language, wait targets, stage ownership, and
   unresolved barriers before an LLM is called.
2. The patient-advocate role extracts the patient's workflow need and unanswered questions.
3. The operations-coordinator role drafts exactly one actionable hospital handoff.
4. The local policy engine checks scope, owner allowlisting, and prohibited clinical language.
5. The safety-reviewer role independently reviews the draft.
6. Any model, parsing, policy, or review failure falls back to deterministic guidance.
7. A hospital worker approves or dismisses the proposal; Polaris never executes it.

Each role has a strict Pydantic contract. Agent traces, policy checks, model identity, timings,
and fallback status are stored inside the corresponding `guidance_proposed` event.

## Trust boundaries

- Patient and hospital timeline text is untrusted data.
- Hermes is an untrusted reasoning dependency whose output must pass schemas and policy.
- The browser is an untrusted client; strict deployments authenticate server-side.
- Hospital systems sit behind `HospitalAdapter`; the provided FHIR adapter is read-only.
- Human approval is the only boundary through which a proposal can become work.

## Portability

The canonical case model deliberately contains only workflow concepts. Vendor-specific FHIR,
HL7 v2, scheduling, transport, and messaging mappings belong in adapters. Core agent roles do
not know the hospital vendor or EHR implementation.

