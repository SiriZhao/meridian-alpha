# Controlled Improvement — Batch 2

Engineering pathway PASS; real production acceptance BLOCKED. No real LLM
availability or recommendation authority is claimed.

## Resume and changes

Starting commit `fa96d86`, branch `astra/controlled-improvement-batch2`. The
interrupted daily_research draft and application changes were continued. Baseline
337 tests passed. Implementation commits: `f85e478` contracts/orchestration,
`c34e717` canonical integration/reports/tests, `208c256` diagnostic and test isolation
fixes. Ending implementation commit: `208c256a1e7eeeaeb680244281fe2a452e123cf6`.
The subsequent documentation commit records this evidence; its hash is in Git log.
No push. User report is excluded from commits.

See [actual architecture and ADR](adr/ADR-010-canonical-advisory-research.md).
Canonical daily now calls validated public advisory research before the existing
deterministic closure and passes ResearchDecisionContext into it. The same decision
and authority boundaries remain; no optimizer, strategy or execution change.
JSON contains research input references, output, provider request status/times,
decision context, stage diagnostics and seven gate results. Markdown shows operator
statuses and literal model inference. Existing SQLite v2 payloads store these
records; no migration. CLI exits 0/2/3 and Windows launcher remain compatible.

## Evidence

- Final pytest: **354 passed, 17.42 s**; Ruff PASS; Pyright **0 errors / 0 warnings**.
  Commands use `.venv/Scripts/uv.exe run --no-sync` (no dependency synchronization).
- New tests exercise HTTP success/auth/rate limit/5xx/timeout, retry bounds,
  malformed/schema/citation failure, decoded credential echo, prompt allowlist,
  fixture/live boundary, replay hash/age/future receipt, canonical failure/pass
  persistence, Windows Chinese/space/# paths and gate blocking. Bullish and bearish
  outputs produce identical deterministic decisions; delayed decisions reject
  expired quotes. Existing sealed authority tests remain green.
- Future fixture observations formerly could raise while constructing the research
  envelope. They now produce BLOCKED diagnostics with zero HTTP attempts. Market
  stage status also reflects freshness instead of merely the existence of quotes.
- Real isolated runtime: init and doctor PASS; missing-snapshot daily runtime PASS,
  recommendation BLOCKED. Actual public requests: Yahoo STALE, Stooq UNAVAILABLE.
  Live LLM **NOT_RUN**, zero actual LLM requests: validated fresh inputs absent.
  No claim about credential availability was inferred. Fixture requests are labeled
  FIXTURE and do not count as production acceptance.
- Repository/installed Skill synchronized after comparison, installed copy backed up.
- [Machine summary](evidence/controlled-batch2-summary.json) and
  [real probe evidence](evidence/controlled-batch2-reality.json).

## Test contamination discovered and contained

The pre-existing Gate 6G test called a legacy runner that writes repository reports.
During baseline/full checks it refreshed two checked_at fields in the already dirty
`reports/gate6g-quote-preflight.json`. The original uncommitted timestamps were not
captured and are not guessed or restored from HEAD. The file remains uncommitted.
The test now redirects REPORTS to tmp_path and asserts the repository report is
byte-for-byte unchanged. The final full suite passed with this isolation in place.

## Remaining limitations

No accepted real Host snapshot, fresh market observations, live research response,
certified research or certified execution quote. Public research is advisory, not
the existing sealed certified lane. Citation validation cannot prove narrative truth.
The shared HTTP socket timeout is bounded per attempt but is not a strict process
deadline; the 128 KiB acceptance check occurs after the legacy helper reads bytes.
Replay requires the original explicit artifact; no automatic prior-day reuse. Audit
and report files retain separate persistence boundaries. No broker actions exist.

## Batch 3 acceptance preparation

Preparation is READY; promotion remains BLOCKED. Next work is acceptance, not a new
strategy or model. Reuse the canonical entry point and isolated runtime:

1. Validate a newly supplied real sanitized Host envelope and authorized provenance;
   do not manufacture or re-ID historical facts. This requires external input.
2. Run actual public probes during an appropriate session; retain timestamps,
   provenance and both provider failures. Closed-session evidence cannot be relabeled.
3. With explicitly enabled existing research settings and eligible inputs, run
   canonical daily and retain LIVE_HTTP schema-validated response evidence. Check
   model identity, citations, request/receipt times, latency and failure behavior.
4. Evaluate existing certified research/evidence and manual gate requirements
   independently; advisory AVAILABLE is not authorization. No broker execution.
5. Compare report/SQLite artifacts and rerun the core checks before any acceptance
   promotion. Preserve all BLOCKED results; do not substitute fixture acceptance.

Daily command stays `scripts/run_meridian.ps1 daily --snapshot <absolute-file> --json`.
There is no safe live acceptance step to execute without the external inputs above.
