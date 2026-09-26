# Agents That Act — submission brief

## Project

**Polaris** is a patient-owned, hospital-agnostic coordination agent. It keeps the patient informed
and mobile while isolated hospital orchestrators prepare departments in parallel. It acts only on
allowlisted logistics and routes emergencies or clinical questions to licensed humans.

- Source: <https://github.com/gowtham66867/Polaris>
- Live AWS demo: <http://ec2-65-0-108-126.ap-south-1.compute.amazonaws.com/>
- Independent Cloud Run demo: <https://polaris-guidance-mb3wwhqg6q-el.a.run.app/>
- Presentation: [Polaris-Agents-That-Act-Submission.pptx](Polaris-Agents-That-Act-Submission.pptx)
- Recording script: [DEMO_RECORDING_SCRIPT.md](DEMO_RECORDING_SCRIPT.md)
- TrueForge agent package: [skill](../trueforge/polaris-care-coordinator/SKILL.md) and
  [saved-agent instructions](../trueforge/AGENT_INSTRUCTIONS.md)

## What the agent does

1. Evaluates deterministic emergency, clinical-question, consent, and isolation gates.
2. Runs a three-role harness: patient advocate, hospital operations coordinator, and independent
   safety reviewer.
3. Selects one non-clinical coordination action, validates it against local policy, and fails closed
   to deterministic guidance if a provider, schema, policy, or review step fails.
4. Lets a hospital worker approve or dismiss the action; approval advances the synthetic workflow
   or opens a named escalation and records an immutable audit event.
5. Coordinates multiple hospitals without combining their records: disclosures are scoped,
   consented, time-limited, and logged.

## Verified engineering evidence

The repository quality gate currently passes with:

- 66 automated tests.
- 92% branch-aware coverage, above the enforced 80% minimum.
- Ruff lint and formatting checks.
- Strict mypy type checking.
- 8/8 adversarial safety-evaluation scenarios.

The presentation's 50-minute manual baseline, 9-minute Polaris result, and 41-minute difference
are an explicitly labeled synthetic counterfactual simulation. They are not clinical evidence or a
measured hospital outcome. Operational outcomes remain pilot targets until a real hospital study
establishes them.

## 3-minute judging path

1. Open the live AWS demo and show the patient and hospital views sharing one synthetic journey.
2. Generate guidance to expose the advocate → coordinator → safety-review harness trace.
3. Approve the safe action and show the stage/handoff plus immutable timeline event.
4. Open the multi-hospital scenario: demonstrate scoped disclosure, a private schedule conflict,
   specialist backup routing, and surge escalation without sharing the other hospital's identity.
5. Run the prompt-injection challenge and emergency/clinical-question examples to show that
   deterministic gates override untrusted timeline text and model output.

## Reproduce the quality receipt

```bash
uv sync --extra test --locked
make quality
```

GitHub Actions executes the same command on every push and pull request.

## Organizer checklist

- [x] Public GitHub repository with visible commit history.
- [x] MIT license, setup instructions, and `.env.example`.
- [x] Concise solution writeup in the README.
- [x] TrueForge skill and agent configuration committed.
- [ ] Public Google Drive demo video, no longer than 3:00, including at least 0:30 of TrueForge.
