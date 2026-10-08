# Read-only research terminal v1

Use the Quant worktree on `codex/research-terminal`; a main-based checkout does
not contain this integration until independently reviewed and merged. Use its
Python 3.12 `.venv`, existing `uv.lock` and checked-in policies.

```powershell
.\.venv\Scripts\python.exe -m meridian terminal <request.json>
.\.venv\Scripts\python.exe -m meridian terminal <request.json> --json
.\.venv\Scripts\python.exe scripts/validate_terminal_artifacts.py
.\.venv\Scripts\python.exe scripts/validate_repo.py
.\.venv\Scripts\python.exe -X utf8 scripts/research_terminal_example.py
```

`SYNTHETIC_EXAMPLE.txt` is generated from the unchanged archived engineering
dataset, not current market or a real account. To exercise the ordinary CLI,
use the example script's `--request` stdout as an isolated request file.

The explicit request is a `QuantTerminalRequest` from the named schema bundle
`schemas/research-terminal.v1.schema.json`. It contains a timezone-aware
`analysis_cutoff`, unique `symbols`, project-owned `histories`, optional dated
metadata and `diagnostic=false`. Supply SPY. Public/raw/incomplete history
produces a truthful blocked packet. Never change certification fields to get
a score. Diagnostic fixtures explicitly require `diagnostic=true` and remain
SYNTHETIC_DIAGNOSTIC; no fixture is current market evidence.

The command writes only stdout. It neither loads nor initializes a paper
account, runs Doctor, calls a provider/model, generates canonical reports or
creates orders. The launcher still selects its project interpreter; launching
through PowerShell does not grant host approval. Canonical Doctor/paper remain
the independently approved-host workflow in the daily operator runbook.

## Views and decisions

| View | Source and interpretation |
|---|---|
| Market overview | Historical SPY regime/cutoff; current quote and breadth explicitly unknown |
| Quant explorer | Actual V2.2 packet, contributions, exclusions, input/policy/engine hashes |
| Portfolio risk | In-memory what-if via MCP/Python, or authorized snapshot blocker; no account fabrication |
| Research workspace | GPT NOT_RUN until explicitly reviewed; numerical packet remains inspectable |
| Decision console | Conservative HOLD/WAIT research categories, no entry price or authorized action |
| Experiment laboratory | Financial evidence status and existing sealed Quant inspection command |
| Operational health | Observed workflow status; provider/model/paper NOT_PROBED/NOT_RUN, broker DISABLED |

For richer observed-price/scenario briefs, `generate_decision_brief` joins a
same-cutoff `DailyResearchInput` and validated native result. Each price retains
source/time/ID and public certification. Stale prices disappear from current
facts. Quant and GPT remain separate; disagreement is retained, speculative
probabilities are omitted, and missing execution inputs require waiting.

`review_terminal` is an explicit Python integration point into the existing
bounded native chain. The Skill uses the active assistant instead of starting
nested calls. The application model profile and timeout are supplied by its
existing ResearchSettings. A terminal input-byte/token-bound rejection does
not erase the deterministic brief. Native CLI ancestry/host restrictions from
Mission 3 remain; this change does not claim external live GPT acceptance.

The recovered checked-in application profile is `gpt-5.6-luna` with `low`
reasoning and `live_enabled=false` in `policies/models.yaml`. That profile is
distinct from the coding assistant used to develop this branch. Mission 4 does
not change the selected model, enable live inference or consume actual model
quota. Injection/schema/failure tests use the existing fake runtime. Before
external acceptance, inspect the effective runtime overrides and follow the
Mission 3 normal-terminal harness; do not treat model configuration as an
observed successful model call.

## Read-only MCP catalog

| New tool | Input | Result / refusal |
|---|---|---|
| `quant_research_snapshot` | QuantTerminalRequest; <=8 symbols, <=9 histories, <=800 bars each, <=2MB | Full existing factors/ranks/regime/constrained targets; AVAILABLE, SYNTHETIC_DIAGNOSTIC or BLOCKED; null rejected ranks |
| `portfolio_what_if` | Sanctioned in-memory Schwab-Paper account, <=20 desired weights, dated metadata, <=40 shocks | Current/preferred/feasible fractions, constraints, declared shocks and cost components; RESEARCH_ONLY/BLOCKED; no raw dollar amounts |
| `research_evidence_trace` | Same request plus exact evidence ID | Recomputed factor/provenance lineage, FOUND/NOT_FOUND; no arbitrary file lookup |

Reuse existing `company_facts`, `event_evidence`, `macro_context`,
`market_snapshot`, `portfolio_context`, `risk_analysis`, `forward_evidence`,
`audit_lookup`, `runtime_status` and validated web tools. These tools are not
duplicated. Legacy aliases stay for compatibility. `quant_metrics` remains an
unverified caller-bar diagnostic, not V2.2 or an adjusted-price attestation.

`market_snapshot` is bounded to four unique valid symbols with existing provider
timeouts; its MCP path disables quote-cache/health writes and only reads valid
historical cache. SEC defaults have no persistent cache. Runtime status skips
write/subprocess probes, uses guarded SQLite mode=ro and never creates missing paths.
WAL-mode databases or existing journal/coordination files return
`READ_ONLY_JOURNAL_REVIEW_REQUIRED` before queries. No checkpoint, journal-mode
change or immutable snapshot shortcut is performed. Resolve an active writer
through the approved operator workflow; do not delete its journal files. OS
read-only permissions remain necessary against concurrent mode reconfiguration.
Audit lookup distinguishes missing runs from unavailable/schema-review storage.
MCP tools cannot perform host-approved Doctor or paper runs.

## Recovery and observability

See CHECKPOINT.json for base/branch, completed checks and exact next action.
Revert the reviewed Mission 4 commits on a development branch to roll back;
no account migration/reset or policy switch is involved. Do not rewrite Git.

Terminal telemetry measures Quant, what-if and report wall time separately,
cache hit, calculations, provider requests and model calls. Deterministic
cache keys bind cutoff/history/policy/engine, TTL <=300s, <=32 entries, memory
only. Cached facts are never relabelled as fresh model conclusions. New cutoff
or changed input misses the cache. The local calculation deadline is checked
at phase boundaries; it does not forcibly interrupt a running Python kernel.

Native scorecards deduplicate shared invocation IDs for wall time/token usage,
show cited claims, evidence coverage, skeptic challenges, disagreement, failures
and logical-stage completion. Missing token/cost/review-time measurements remain
null. No return improvement or production latency SLO is inferred from fixtures.
Provider latency/failures remain in existing operational diagnostics. No new
research inference retries or background monitor are introduced.

Remaining blockers: qualified adjusted real history, source authentication,
calibrated expected return/probabilities, ETF look-through, complete correlations,
live external operator acceptance and independently measured review-time benefit.
Financial status remains ALPHA_NOT_YET_DEMONSTRATED.

On Windows, full repository validation includes tests that terminate their own
child process trees. This session reproduced a restricted-sandbox failure of
that test (about 60s), while the same frozen source passed it on the approved
host (1.87s). Use approved host execution for that validation when the sandbox
cannot terminate descendants, keeping MERIDIAN_HOME and MERIDIAN_CACHE in
isolated workspace directories. Do not skip or weaken the timeout assertion,
run a real GPT harness inside a forbidden ancestry, or use canonical runtime
state as a test fixture.
