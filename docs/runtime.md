# Runtime operations

Canonical CLI: `meridian` or `python -m meridian`. Windows launcher:
`scripts/run_meridian.ps1`. See README for the supported arguments.

Runtime home: absolute MERIDIAN_HOME, otherwise LOCALAPPDATA/MeridianAlpha on
Windows. DB, reports, logs, cache and audit state all use RuntimePaths.
The installed wheel includes policies and does not require a writable checkout.

Doctor probes real directory creation/read/write/delete, Python/dependencies,
config, timezone and SQLite schema/integrity. Optional adapter presence is
UNKNOWN provider availability, never a successful live probe.

Fresh DB is PENDING in doctor; daily applies the existing SQLite v1 migration.
Init is idempotent. A newer schema is rejected. Migration and audit connections
are explicitly closed, including on failure. No Alembic or external DB exists.

Each daily invocation logs startup, DB/preflight, market retrieval, analysis,
run ID and output paths. Account/credential contents are never logged.
Errors return a category, code, next action and log directory. Preserve user DB
and reports when troubleshooting; there is no destructive automatic recovery.

Live public retrieval closes the analysis cutoff after reception. Replay keeps
a fixed cutoff and rejects observations received afterward. Public inputs are
not certified execution quotes. Closed-market stale quotes remain blocked.
