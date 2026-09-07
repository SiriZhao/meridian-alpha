# Runtime operations

Canonical CLI: `meridian` or `python -m meridian`. Windows launcher:
`scripts/run_meridian.ps1`. See README for the supported arguments.

Runtime home: absolute MERIDIAN_HOME, otherwise LOCALAPPDATA/MeridianAlpha on
Windows. DB, reports, logs, cache and audit state all use RuntimePaths.
The installed wheel includes policies and does not require a writable checkout.

Doctor probes real directory creation/read/write/delete, Python/dependencies,
config, timezone and SQLite schema/integrity. Optional adapter presence is
UNKNOWN provider availability, never a successful live probe.

Fresh DB is PENDING in doctor; daily applies the SQLite v1 → v2 migration.
Init is idempotent. A newer schema is rejected. Migration and audit connections
are explicitly closed, including on failure. No Alembic or external DB exists.

Each daily invocation logs startup, DB/preflight, market retrieval, analysis,
run ID and output paths. Account/credential contents are never logged.
Errors return a category, code, next action and log directory. Preserve user DB
and reports when troubleshooting; there is no destructive automatic recovery.

Live public retrieval closes the analysis cutoff after reception. Replay keeps
a fixed cutoff and rejects observations received afterward. Public inputs are
not certified execution quotes. Closed-market stale quotes remain blocked.


## Recommendation readiness and persistence

`RecommendationReadiness` extends the existing host readiness vocabulary.
UNKNOWN/NOT_RUN/DEGRADED never aggregate to recommendation PASS. Research,
recommendation and manual execution are distinct derived outcomes; these
are diagnostics, not a replacement for the sealed seven-gate authority.
Canonical public quotes remain uncertified. Canonical research is an optional
validated advisory stage; disabled configuration remains NOT_RUN.
Policy validation is not certification of the operational placeholder sectors.

SQLite v2 adds `snapshot_receipts` (only ID/content hashes and first-seen time)
and `run_readiness` (immutable readiness, snapshot and provider diagnostics).
Existing v1 databases upgrade transactionally; user tables are preserved and
newer schemas rejected. No second database or Alembic is introduced.
Concurrent submissions can claim a snapshot only once. A failed downstream run
retains its claim: obtain a new snapshot instead of silently retrying old facts.
Validate-only checks novelty without claiming. A new ID alone does not make
identical snapshot facts new. The Host digest proves consistency, not identity.

Freshness thresholds come from existing data policy. Source times, received times,
cutoff, session and cache provenance remain explicit. Replay excludes receipt
beyond its fixed cutoff; live cutoff closes after retrieval. Session calendar
handles ordinary holidays, DST and common half-days, not unscheduled closures.
Previous-session close context is diagnostic only; stale prices stay blocked.
Historical daily-bar freshness counts sessions, not elapsed calendar days.

Rejected account input produces JSON, Markdown and a DB diagnostic run. Invalid
market fixtures likewise persist blocked evidence and retain exit 3. If runtime
storage itself is unavailable, JSON/exit diagnostics may be the only possible
output; no persistence success is claimed. CLI compatibility remains 0/2/3.
