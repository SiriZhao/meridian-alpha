# Meridian Alpha project constitution

## Scope

Meridian Alpha is a US-equity, AI-assisted portfolio decision system. Its
terminal boundary is a manual limit-order ticket for a human to enter at their
broker. It has no brokerage execution capability and must never grow one.

## Permanent principles

1. Schwab actual account state is the source of truth.
2. Never assume yesterday’s recommended orders were filled.
3. Never infer fills from recommendations.
4. Every trading day starts from a newly supplied AccountSnapshot.
5. No look-ahead data is permitted.
6. LLM output never directly determines share quantity or limit price.
7. Portfolio sizing and order generation must be deterministic.
8. Human approval is required for every real order.
9. No automatic brokerage execution is permitted.
10. If account or market data freshness cannot be verified, executable order output must be blocked.
11. Sensitive account data must not be persisted by default.
12. Never fabricate FinRL-X model outputs.
13. Never fabricate missing market/account data.

## Hard prohibitions

- Do not add broker execution, broker login, or brokerage-write code.
- Do not directly couple the core to the Schwab Trading API.
- Do not add, print, read, commit, or log credentials, tokens, account numbers,
  or other secrets. Use environment/secret-manager references only when a
  later, explicitly approved integration needs them.
- Do not make research-agent prose the source of order quantities, position
  sizes, or prices.
- Do not bypass freshness gates, risk checks, reconciliation, or manual
  approval.
- Do not persist raw AccountSnapshot data by default.

## Required dependency and interface discipline

- The core depends on project-owned domain protocols, never on a broker SDK,
  TradingAgents, FinRL-X, or a data-provider SDK.
- External frameworks are optional adapters, pinned by version/commit and
  invoked behind explicit interfaces.
- All future market data must carry provenance and timestamps; unavailable or
  unverified data is represented explicitly, never invented.
- Changes to system boundaries require an ADR.

## Codex canonical-runtime execution boundary

Treat the following user intents as the canonical `Schwab-Paper` daily
workflow: “运行今日 Meridian Alpha”, “运行今天的 Meridian Alpha”, “今日 paper
run”, “运行 Schwab-Paper”, and equivalent wording.

The canonical runtime is `E:\MeridianAlphaRuntime`, the canonical database is
`E:\MeridianAlphaRuntime\db\meridian.sqlite3`, and the canonical account is
`Schwab-Paper`. Any command that can mutate that runtime MUST use Codex's
approved host execution mechanism. This includes `paper run`, canonical daily
runs, ledger changes, report generation, cache atomic writes, migrations,
runtime write probes, and `doctor` because it performs write probes. In Codex
environments that expose shell escalation, invoke these commands with
`sandbox_permissions=require_escalated` (or the equivalent approved-host
control). Never first try a canonical write command in the restricted sandbox.

Approval is a prerequisite, not an error-recovery step. While approval has not
been granted, do not run the command and report `HOST_APPROVAL_REQUIRED`. If
approved host execution is unavailable, rejected, capacity-limited, or cannot
enter a host context, report `HOST_EXECUTION_UNAVAILABLE`. Never fall back to a
restricted sandbox, and do not classify an unattempted host command as
`MERIDIAN_DATABASE_INIT_FAILED` or `STORAGE_UNAVAILABLE`. If a command really
runs in an approved host context and returns a storage failure, preserve its
actual diagnostic.

For a canonical daily request, follow this order:

1. Confirm the repository root, project `.venv`, configured canonical runtime,
   `Schwab-Paper` account, current date, and Meridian trading-calendar policy
   without changing the runtime.
2. Request approved host execution before any canonical-runtime write or write
   probe.
3. In the approved host context run
   `.\scripts\run_meridian.ps1 doctor --json`. Continue only when it returns
   `PASS`.
4. In the same approved host boundary run
   `.\scripts\run_meridian.ps1 paper run --account Schwab-Paper --json`.
5. Read the canonical result and report status, run ID, trading date, account,
   research status, market-data status, decision, orders, fills, NAV, blockers
   or degraded reason, and report path.
6. Verify that the run used the canonical root and account, did not create a
   duplicate canonical day, and produced no broker or live-order side effect.

Both commands require approved host execution. If the product grants approval
per command, obtain approval for each; neither command may run in the sandbox.
Do not force a historical trading date or create a paper day for testing. In
particular, do not recreate the existing 2026-09-18 canonical run. Repository
tests and read-only source inspection may run in the sandbox when they do not
write the canonical runtime.

The repository launcher selects the project Python and runtime configuration;
it does not cross the Codex sandbox boundary by itself. The MCP server exposes
Meridian tools and delegation surfaces; it is not an approved-host bridge.
Project instructions and the Meridian skill must therefore route canonical
writes through Codex host approval before invoking the launcher.

## Quality gates

## Development quick start

- Python 3.12; create `.venv`, then install with `python -m pip install -e ".[dev]"`.
- Run `python scripts/validate_repo.py` using that environment: Ruff, Pyright,
  full offline pytest, and CLI smoke. See `DEVELOPMENT.md` for fresh-clone steps.
- Architecture: Market/Data -> Research -> Decision -> Execution Plan -> Paper/Ledger.
- Core code: `src/meridian`; regression coverage: `tests`; contracts and policy:
  `schemas`, `prompts`, `policies`. Windows launchers live in `scripts`.
- Tests must isolate runtime state; never use the canonical database for tests.
- Default account: `Schwab-Paper`; broker submission: `DISABLED`.
  HSBC holdings and credentials are outside Meridian Alpha.
- Start development branches from `origin/main`; preserve user changes and
  remote history. Completion requires full validation, reviewed diff, clean
  working tree, and matching local/remote SHA when publishing is authorized.

## Individual checks

Run the applicable checks before handoff:

```powershell
uv run pytest
uv run ruff check .
uv run pyright
```

Do not push a remote or create a release tag unless the user explicitly asks.
