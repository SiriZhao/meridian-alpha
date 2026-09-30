# Meridian Alpha development

## Setup

Use Python 3.12. From a fresh clone, run `python -m pip install -e ".[dev]"` or
`uv sync --group dev`. The project does not require broker credentials or an
external runtime for tests.

## Validation

Run the cross-platform entrypoint:

```text
python scripts/validate_repo.py
```

It runs Ruff, Pyright, the complete offline pytest suite, and a CLI help smoke
test. Pytest uses the repository-local `.pytest-tmp` directory, which is
ignored by Git and avoids stale system temp permissions on Windows.

## Layout and boundaries

- `src/meridian`: domain, pipeline, research, decision, paper and reporting code
- `tests`: deterministic unit, integration and regression coverage
- `scripts`: bounded diagnostics and validation entrypoints
- `policies`, `prompts`, `schemas`: packaged policy and contract inputs
- `docs`: architecture, operations and audit records

Meridian is paper-only. The canonical account is `Schwab-Paper`, broker
submission is always `DISABLED`, and GPT/Codex has no broker, order or ledger
authority. HSBC holdings are outside this system.

## Windows and Linux

Core Python code uses `pathlib`, UTC-aware timestamps and argument-array
subprocesses. Windows launcher scripts are adapters around the same Python CLI;
Linux CI runs the identical validation entrypoint. Codex child processes are
started in an isolated process group so timeout cleanup covers descendants.

## Git workflow

Keep `main` stable and create `chore/*`, `fix/*`, or `feature/*` branches from
it. Do not force-push, rewrite history, enable a broker, or commit runtime data,
credentials, caches or `.env` files.
