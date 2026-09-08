# Meridian Alpha

US-equity portfolio decision support. All current outputs are research-only;
there is no broker execution and a DRAFT is not authorization to enter an order.

## Install (Windows PowerShell)

Use Python 3.12 and uv. From this checkout:

```powershell
uv sync --group dev --inexact
```

`--inexact` preserves already installed optional research packages. If uv is not
on PATH but the existing environment is present, use `.\.venv\Scripts\uv.exe`.

## Configure

Runtime defaults to `%LOCALAPPDATA%\MeridianAlpha`, independent of the working
folder. Optionally set `MERIDIAN_HOME` to an absolute writable user directory.
Policies come from the checkout (or the installed wheel); `MERIDIAN_POLICY_DIR`
selects an explicit policy directory. Do not put credentials or raw account
identifiers in configuration or input files.

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
comes from the actual HTTP response and schema validation; disabled configuration
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

On its first use it creates `Schwab-Paper` with USD 100,000.00 cash. Later
runs load the same SQLite ledger and never reset it. The command creates a
fresh internal `PAPER_LEDGER` account observation, calls the existing canonical
daily path, attempts the configured DeepSeek advisory stage through its normal
credential boundary, evaluates deterministic decisions and gates, and simulates
only eligible paper fills. It writes canonical and Schwab-Paper JSON/Markdown
reports under the runtime home.

Paper fills require a NYSE regular session, fresh public market observations,
validated advisory research, a completed deterministic decision and current
portfolio constraints. Closed/stale/unavailable inputs return `PAPER_BLOCKED`
with evidence; no fixture, prior LLM response or stale quote is substituted.
Public quotes remain `PUBLIC_RESEARCH_QUOTE`, never certified execution quotes.
Paper execution does not grant manual authority and broker submission remains
disabled.

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

Core regression: `uv run --no-sync pytest`, `uv run --no-sync ruff check .`,
`uv run --no-sync pyright`. The subprocess E2E creates a fresh runtime outside
the checkout, runs twice, checks SQLite integrity and persisted reports.

See [runtime baseline](docs/runtime-baseline.md), [maintenance backlog](MAINTENANCE.md)
and [runtime details](docs/runtime.md). Historical Gate/ROUND documents remain
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
