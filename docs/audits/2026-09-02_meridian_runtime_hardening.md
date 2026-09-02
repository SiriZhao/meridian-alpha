# Meridian runtime hardening audit — 2026-09-02

## Baseline

- Baseline commit: `bbf1a4f`.
- Worktree already contained an unrelated modification to
  `reports/gate6g-quote-preflight.json`; it was not changed.
- `python --version` resolved to 3.14.3, while the project declares and
  production diagnostic requires Python 3.12. The project `.venv` is 3.12.14.
- `uv` was not on PATH. `uv.lock` exists but could not be refreshed here.
- No Alembic configuration exists. The existing SQLite audit store owns schema
  version 1 through its internal migration table.

## Implemented and verified

- Added `RuntimePaths`: Windows defaults to
  `%LOCALAPPDATA%\MeridianAlpha`, supports an absolute `MERIDIAN_HOME`, and
  exposes isolated data/db/cache/reports/logs/runs/audit/config paths.
- Added a local-only JSON runtime diagnostic and a thin PowerShell launcher.
  The diagnostic has no provider probe, network access, model startup, or
  secret output. It reports runtime permissions, SQLite, the observed schema
  migration state, config, timezone/calendar, optional module presence, and
  dependency availability.
- Added isolated runtime, environment override, secret redaction, startup
  timing, and temporary database migration tests.

## Actual validation

- Focused tests: `6 passed` (`tests/test_runtime_diagnostics.py` and
  `tests/test_runtime_database.py`, after their addition).
- Prior full regression before the final two test additions: `282 passed in
  8.19s` using `.venv\Scripts\python.exe -m pytest -q`.
- Focused Ruff: passed after mechanical formatting. Focused Pyright: `0
  errors, 0 warnings, 0 informations`.
- Compile/import smoke: completed before full regression.
- Local diagnostic timing: `78.0 ms`; it reported `DEGRADED` only because the
  fresh temporary database was intentionally uninitialized.

## Remaining blockers / limits

- **EXTERNAL_BLOCKER:** this Codex session's file-edit helper fails when it
  re-reads any pre-existing workspace file (`apply deny-read ACLs`). Therefore
  no existing CLI, MCP, audit, daily packaging, Docker, pyproject, or README
  file was overwritten. This audit deliberately does not claim those entry
  points have been rewired to `RuntimePaths`.
- Production Python is required to be 3.12; the host PATH currently selects
  3.14.3. The project venv provides a verified 3.12.14 alternative.
- Alembic is not currently part of the repository. The existing audit store
  has an internal schema migration at version 1; introducing Alembic requires
  an ADR and a safe, tested migration plan rather than inventing revision
  history.
- The runtime diagnostic is additive until its commands can be registered in
  the established `meridian` CLI and MCP paths.

## Git state

Final commit: pending. Only new runtime hardening files are intended for the
commit; the pre-existing report modification remains excluded.
