# Meridian Alpha

US-equity portfolio decision support. All current outputs are research-only;
there is no broker execution and a DRAFT is not authorization to enter an order.

Meridian Alpha is independent from Personal Alpha Terminal. No implementation,
runtime state, account semantics, or migration path is shared between them.
Meridian remains `PAPER_ONLY`; `AUTO_EXECUTION = FALSE`; real broker writes and
live orders are unsupported.

The pipeline is `Market/Data -> Research -> Decision -> Execution Plan -> Paper/Ledger`.
Research supplies grounded analysis; deterministic policy controls sizing,
prices, risk gates and simulated fills.

Current canonical operation is one application service shared by CLI, the
PowerShell launcher, the Skill paper command, and MCP Host-envelope delegation.
Daily reports expose independent `DATA`, `RESEARCH`, `DECISION`, `RISK`,
`PAPER`, and `HOST_LLM` status dimensions. A Host research result is bound to
its job, as-of time, symbol universe, quote timestamps, evidence IDs, market
snapshot ID, and model/runtime provenance. Resume classifies market movement as
`EXACT`, explicitly `REVALIDATED`, or `REFRESH_REQUIRED`; market drift is not
reported as a generic LLM failure.

Historical maintainer acceptance on 2026-09-11: **BLOCKED_WITH_EVIDENCE**.
Source validation and a real clean wheel installation passed. The one fresh
GPT-6 Astra acceptance session hit its usage limit before reading the Skill or
calling tools; SEC retrieval also returned HTTP 403. This is not a production
research acceptance. See [final review](reports/meridian-astra-final-review.md)
and [clean installation](reports/meridian-clean-install-acceptance.md).

Current development includes canonical report projections, provider-failure
telemetry, crash-safe paper ownership and an isolated
[alpha research laboratory](docs/alpha-lab.md). Operational scoring still uses
positive daily return; successful GPT consultation is not evidence of LLM
influence on target weights. Reviewed research closes and descriptive signal
evaluation do not certify execution quotes or demonstrate positive alpha.
See the [Phase 4 checkpoint and acceptance report](docs/audits/2026-10-08-phase4-alpha-lab-acceptance.md)
for executed checks, remaining work and data limitations.

## Install (Windows PowerShell)

Use Python 3.12 and uv. On Windows, select it explicitly with `py -3.12`; on
Linux use `python3.12`. From this checkout:

```powershell
uv sync --frozen --group dev --inexact
```

`--inexact` preserves already installed optional research packages. If uv is not
on PATH but the existing environment is present, use `.\.venv\Scripts\uv.exe`.

For an installed wheel, use `meridian doctor --json` and `meridian init --json`
from its Python 3.12 environment. The checkout and its PowerShell launcher are
not required for wheel operation. Mutable state uses `RuntimePaths`.

## Configure

Runtime defaults to `%LOCALAPPDATA%\MeridianAlpha`, independent of the working
folder. Optionally set `MERIDIAN_HOME` to an absolute writable user directory.
Policies come from the checkout (or the installed wheel); `MERIDIAN_POLICY_DIR`
selects an explicit policy directory. Do not put credentials or raw account
identifiers in configuration or input files.

## Market research evidence

The operational quote path is **Yahoo → Nasdaq fallback → freshness-validated
cache → explicit unavailable**. Provider attempts and primary failures remain
in JSON; provider health never grants authority. Public quotes remain
`PUBLIC_RESEARCH_QUOTE`, with execution quote certification `BLOCKED`.
Research evidence separately supports cache, structured providers and trusted-web
submissions. Public data and Astra-supplied
web evidence are research-only and never execution quotes. When Yahoo is stale
or unavailable, Astra may browse trusted sources and submit compact facts to
the read-only `validate_market_evidence` tool. Meridian validates source URLs,
source tier, timestamps, currency, corroboration and conflicts; it does not
browse or call another model. Historical OHLCV needs an explicit machine-readable
table, CSV or JSON source. Narrative text cannot create bars or technical metrics.

## Doctor

```powershell
.\scripts\run_meridian.ps1 doctor --json
```

A missing database is PENDING, and daily initializes it automatically. Other
FAIL checks require correction before analysis. `meridian init --json` is also
available for explicit, idempotent database initialization.

## Run

Supply a fresh sanitized HostAccountSnapshotEnvelope from your authorized source:

```powershell
.\scripts\run_meridian.ps1 daily --snapshot "C:\Inputs\today.json" --json
```

The launcher delegates to `python -m meridian`; installed `meridian` uses the
same CLI. It runs DB initialization, doctor, public market retrieval,
deterministic portfolio/risk analysis, audit persistence, and reports. JSON
includes typed `readiness`, `snapshot_provenance`, actual `provider_probes`,
`next_actions`, warnings/errors, and `output_files`. Reports and
logs are under the runtime home. No raw snapshot is saved by default.

Canonical daily runs structured advisory research when the existing research
policy is explicitly enabled and fresh inputs are available. Research status
comes from a local `codex exec` final response and strict schema validation;
disabled configuration
remains NOT_RUN. Advisory completion does not certify a recommendation. Missing/stale market
inputs block recommendations while still producing a diagnostic report.
No real account snapshot means no real portfolio validation.

For synthetic regression only, add `--market-fixture <synthetic-market.json>`
with a synthetic account. Fixture success is not production verification.
Old `--profile`, `--date`, and `--account-fixture` commands are historical.

## Schwab-Paper daily workflow

For the default persistent paper account, the only daily command is:

```powershell
.\scripts\run_meridian.ps1 paper run --account Schwab-Paper --json
```

`paper run` requires an existing `Schwab-Paper` account. Missing account or
storage returns a blocked result; it never initializes or resets the ledger.
Explicit `paper init` is a separate setup action. Daily runs load the same
SQLite ledger. The command creates a
fresh internal `PAPER_LEDGER` account observation, calls the existing canonical
daily path, invokes the Codex CLI advisory stage through its saved
ChatGPT-managed login, evaluates deterministic decisions and gates, and simulates
only eligible paper fills. It writes canonical and Schwab-Paper JSON/Markdown
reports under the runtime home.

Paper fills require a NYSE regular session, fresh public market observations,
validated advisory research, a completed deterministic decision and current
portfolio constraints. Closed/stale/unavailable inputs return `PAPER_BLOCKED`
with evidence; no fixture, prior LLM response or stale quote is substituted.
Public quotes remain `PUBLIC_RESEARCH_QUOTE`, never certified execution quotes.
Paper execution does not grant manual authority and broker submission remains
disabled.

Canonical operation uses `E:\MeridianAlphaRuntime`. In Codex, both Doctor
and paper run require approved host execution because they write runtime
state. Run Doctor first and continue only on `PASS`; the PowerShell launcher
does not grant host permissions. See [the canonical workflow](docs/canonical-production-workflow.md).

The GPT research layer may perform primary analysis, skepticism, scenarios,
and synthesis. It cannot choose executable quantity or price, mutate the paper
ledger, bypass deterministic risk gates, or acquire broker authority.

TradingAgents remains an optional, disabled-by-default legacy research adapter.
It is not installed by the base runtime and is not part of the canonical daily
path. See the current upstream assessment in
[`docs/tradingagents-upgrade-assessment-2026-09-16.md`](docs/tradingagents-upgrade-assessment-2026-09-16.md).

Useful read-only commands are:

```powershell
.\scripts\run_meridian.ps1 paper status --account Schwab-Paper --json
.\scripts\run_meridian.ps1 paper history --account Schwab-Paper --json
.\scripts\run_meridian.ps1 paper trades --account Schwab-Paper --json
```

`paper init` is idempotent. `paper reset` requires `--confirm-reset` with the
exact account name and is never called by `paper run` or the Skill. See
[Schwab-Paper operations](docs/schwab-paper.md).
## Common errors

- Missing Python: install Python 3.12 and sync dependencies.
- Runtime path failure: set an absolute writable `MERIDIAN_HOME`; rerun doctor.
- Database failure: inspect permissions, locks and schema; preserve the DB.
- Invalid input: use the Host envelope contract and `meridian snapshot validate <file> --json`.
- Market data stale/unavailable: inspect `symbols_missing` and provider health;
  never replace missing quotes with invented prices.

Exit codes: 0 completed operational result, 2 degraded/blocked input, 3 failure.
A zero exit code never grants recommendation or manual-entry authority.
Read `readiness.recommendation_readiness` and `manual_execution_readiness`.
A snapshot content digest does not authenticate the Host source. Repeated
snapshot IDs/facts are explicitly rejected across processes; provide a new
snapshot for each daily run, including after a failed run consumed its input. Use the PowerShell terminal
so diagnostics remain visible; the launcher preserves the process exit code.

## Maintenance

Core regression: `python scripts/validate_repo.py` (or the equivalent `uv run`
commands for pytest, Ruff and Pyright). The subprocess E2E creates a fresh runtime outside
the checkout, runs twice, checks SQLite integrity and persisted reports.

See [runtime baseline](docs/runtime-baseline.md), [maintenance backlog](MAINTENANCE.md)
and [development guide](DEVELOPMENT.md). Historical Gate/ROUND documents remain
for audit only and are not the daily operating instructions.


Controlled Improvement Phase 1 implementation and evidence are recorded in
[phase record](docs/controlled-improvement-phase1.md). Real acceptance remains
DEGRADED/BLOCKED; no certified LLM/quote path is implied by this implementation.

## Forward evidence

Canonical daily freezes append-only, cutoff-bound operational forward evidence
only after an eligible non-fixture decision. It is evaluated on configured NYSE
trading-session horizons and can never promote a strategy automatically. Inspect
its mature sample status with:

```powershell
.\scripts\run_meridian.ps1 forward-status --json
```

See [Forward Evidence Factory](docs/forward-evidence.md) and the
[canonical workflow](docs/canonical-production-workflow.md).

## Quant Engine V2 challenger

V2 adds deterministic point-in-time features, multi-horizon factor scores, SPY
regime dimensions, constrained cost-aware targets and next-open walk-forward
replay. V1 remains canonical; shadow is explicit opt-in and paper review is a
separate, evidence-gated call. No automatic strategy promotion or broker orders.

See [architecture](docs/quant-v2/ARCHITECTURE.md),
[research and complete diagnostic records](docs/quant-v2/RESEARCH_REPORT.md),
[baseline audit](QUANT_V2_BASELINE_AUDIT.md) and
[ADR 0037](docs/adr/0037-quant-engine-v2.md).
Verified financial OOS alpha is **not demonstrated**; synthetic diagnostics are
engineering evidence only.
