# Contributing to Polaris

Polaris is a non-clinical coordination prototype. Changes must preserve the safety boundary:
no diagnosis, treatment advice, result interpretation, clinical reprioritization, or handling of
real protected health information.

## Development setup

```bash
uv sync --extra test --locked
cp .env.example .env
make run
```

Use only synthetic data. Keep credentials in local environment variables or a managed secret
store; never commit them.

## Required quality gate

Run the exact gate used by GitHub Actions before opening a pull request:

```bash
make quality
```

It runs:

1. Ruff lint and formatting checks.
2. Strict mypy type checking.
3. The complete pytest suite with branch coverage and an 80% minimum.
4. The adversarial safety evaluation harness in `evals/run_evals.py`.

Tests should cover the behavioral contract, including the failure or safety path. Changes to agent
prompts, policies, model schemas, action execution, consent, or hospital isolation require a
corresponding test or evaluation scenario.

## Pull requests

- Keep changes focused and explain the user-visible behavior.
- State which safety boundary is affected and how it was verified.
- Include `make quality` results and update documentation when behavior changes.
- Preserve contributor authorship when porting work from another branch.
