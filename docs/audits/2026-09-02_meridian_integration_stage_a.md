# Meridian integration and release closure — Stage A

## Baseline

- Baseline SHA: `ab4c23f`.
- User-owned `reports/gate6g-quote-preflight.json` was present and untouched.
- Inventory: the historical `meridian.cli`, `daily_cli`, `operational_cli`,
  legacy launcher and MCP still exist; only `python -m meridian` is canonical
  in this stage. They are retained pending safe thin-wrapper migration.

## Canonical surface

- `src/meridian/application.py`: `MeridianApplicationService`, a thin facade
  over RuntimePaths, diagnostics, existing SQLite migration, daily closure,
  data status, Dip Scout and forward evidence.
- `src/meridian/application_cli.py` plus `src/meridian/__main__.py`:
  canonical portable commands: version, paths, doctor, init, data-status,
  snapshot validate, daily, dip-scout and forward-status.
- No allocator, risk, market normalization, limit engine, or LLM logic was
  copied into the application layer.

## Init semantics

`python -m meridian init --json` explicitly creates RuntimePaths and invokes
the existing SQLite schema migration. A fresh home returns `INIT_COMPLETE`; a
schema-current home returns `INIT_ALREADY_COMPLETE`. Invalid SQLite returns
`INIT_FAILED`; init does not remove or overwrite the database. Doctor never
initializes the database and reports `PENDING` with a degraded status first.

## Measured smoke

With `MERIDIAN_HOME=.pytest_tmp/integration` and Python 3.12.14:

- version: completed successfully;
- init: `INIT_COMPLETE`, schema 1;
- doctor after init: `PASS`, 31.0 ms, `network_accessed=false`.

## Remaining blockers

- `pyproject.toml` console script still targets legacy `meridian.cli`; the
  protected in-place migration was not performed in this session.
- Existing PowerShell launcher and MCP require thin delegation to
  `MeridianApplicationService` before they become canonical.
- README quick start also needs a safe in-place update.
- Product readiness remains separately blocked by fresh authorized account,
  certified execution quote/manual certificate, and PIT research gaps.
