# Polaris — compliant 3-minute demo recording

Record at 1080p as an MP4. Keep a visible **Synthetic demo data** label on screen; do not show
real patient data, API keys, terminals containing secrets, or private browser tabs. Use the
captions below as narration if audio is unavailable.

| Time | Screen / action | Narration or caption |
| --- | --- | --- |
| 0:00–0:15 | Title card, then the public Polaris demo. | “Polaris is a patient-owned, hospital-agnostic coordination agent. It reduces operational waiting without making clinical decisions.” |
| 0:15–0:40 | Submit the synthetic patient journey. Show the emergency, clinical-question, consent, and hospital-isolation gates. | “Deterministic gates run first. Emergency and clinical requests are routed to licensed humans; actions requiring consent stop.” |
| 0:40–1:05 | Show the three-role trace: advocate, operations coordinator, and safety reviewer. | “The harness proposes one allowlisted logistics action. An independent safety reviewer must approve the proposal before a human worker sees it.” |
| 1:05–1:25 | Use the worker view to approve a safe action. Show the stage update, handoff, and immutable audit event. | “The worker retains control. Approval advances the synthetic workflow and creates an auditable event.” |
| 1:25–1:45 | Open the multi-hospital scenario. Show scoped, time-limited disclosure and a schedule conflict or specialist fallback. | “Each hospital remains isolated. Polaris shares the minimum necessary, consented information; it never merges hospital records.” |
| **1:45–2:30** | **TrueForge at `localhost:8790`: Settings → Skills, Polaris Care Coordinator imported and enabled; then the saved Polaris agent with the same synthetic request, harness instructions, model trace or tool/result view, and human checkpoint. Keep this on screen for at least 45 seconds.** | **“TrueForge is the agent harness used for the judge-facing flow. It loads the Polaris skill and saved-agent instructions, runs the agent session and trace, and pauses for the human checkpoint. The deployed app retains a matching deterministic safety harness so it fails closed if a provider is unavailable.”** |
| 2:30–2:50 | Return to Polaris: run one prompt-injection-like timeline entry and one emergency or clinical request. | “Untrusted timeline text and model output cannot override deterministic gates. Polaris stops and escalates rather than guessing.” |
| 2:50–3:00 | Closing card with repo and live demo URLs. | “The repository is public, MIT-licensed, reproducible, and tested. Polaris makes care operations faster while preserving patient agency and human clinical authority.” |

## Pre-flight checklist

- [ ] Recording is MP4, 1080p, and **3:00 or shorter**.
- [ ] Narration or captions cover the complete video.
- [ ] TrueForge is visible for **at least 0:30** (this script allocates 0:45).
- [ ] All data shown is synthetic; no key, password, or patient data is visible.
- [ ] The final file plays locally before upload.
- [ ] Google Drive sharing is set to “Anyone with the link” before pasting the URL into HackCulture.

