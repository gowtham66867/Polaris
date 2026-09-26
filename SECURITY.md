# Security and clinical-safety boundary

Polaris is a non-clinical coordination prototype. It is not approved to process production
protected health information or to make clinical decisions.

## Enforced controls

- Model outputs are parsed through role-specific schemas with unknown fields rejected.
- Case text is labeled untrusted, normalized, bounded, and checked for prompt injection.
- A deterministic emergency rule runs before any model call.
- A local policy engine independently checks every model-generated action.
- An independent safety-review role must approve the draft.
- Unsafe or malformed output fails closed to deterministic workflow guidance.
- External actions are never executed; approval/dismissal is recorded as a separate event.
- The FHIR adapter is read-only and requires TLS.

## Explicitly out of scope for the MVP

Production use requires an identity provider, RBAC/ABAC, tenant isolation, key management,
encryption and backup policy, consent withdrawal, retention/deletion controls, complete audit
export, rate limiting, dependency/SBOM scanning, clinical governance, incident response, and
jurisdiction-specific privacy and medical-device review.

Report security issues privately to the project owner; do not include patient information.

