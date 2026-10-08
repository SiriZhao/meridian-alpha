# Meridian Alpha development

## Setup

Use Python 3.12 (`py -3.12` on Windows or `python3.12` on Linux). From a fresh
clone, create a 3.12 virtual environment, then run `python -m pip install -e
".[dev]"`, or use `uv sync --group dev`. The project does not require broker credentials or an
external runtime for tests.

For an independent clone on Windows:

```powershell
git clone https://github.com/SiriZhao/meridian-alpha.git
cd meridian-alpha
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe scripts/validate_repo.py
```

On Linux replace environment creation with `python3.12 -m venv .venv`
and use `.venv/bin/python`. These commands install from project metadata;
`uv sync --frozen --group dev` instead installs the checked-in lockfile.
Do not inherit `PYTHONPATH`, runtime overrides, or credentials from another
checkout. CI exercises independent Python 3.12 environments on both platforms.

Nested development worktrees under `.worktrees/` are ignored; do not package or
commit another task's worktree. The [alpha lab](docs/alpha-lab.md) uses isolated
JSON ledgers and read-only CLI inputs, never the canonical runtime. Safe
acceptance is an offline fixture harness with a fixed OPEN-session clock; it
does not verify a fresh live market or native-model invocation.

For Windows environments with restricted system temp/cache ACLs, select a
writable workspace uv cache before installation:

```powershell
$env:UV_CACHE_DIR = Join-Path (Get-Location) '.tmp/uv-cache'
```

Windows subprocess-tree termination must also be validated in a host context
that can terminate its own child processes. Do not skip that regression to
hide sandbox permission failures. Test/lab host validation still uses isolated
workspace runtime paths and never grants broker authority.

For reproducible release/CI validation, install from the checked-in lock with
the same uv version as the Windows bootstrap and CI:

```powershell
python -m pip install uv==0.12.7
python -m uv sync --frozen --group dev
.venv\Scripts\python.exe -m ensurepip
.venv\Scripts\python.exe scripts\validate_repo.py
```

Use `.venv/bin/python` for the final two commands on Linux. After syncing,
`python -m uv` may no longer be installed inside the project environment;
the completed sync is unaffected. Install uv separately for repeated syncs.

## Validation

Run the cross-platform entrypoint:

```text
python scripts/validate_repo.py
```

It checks dependency integrity, Ruff, Pyright, the complete offline pytest
suite, CLI help and `scripts/safe_acceptance.py` in an optimized fresh process.
That smoke uses disposable runtimes, synthetic market/research inputs, no-trade
and simulated-fill paths, duplicate protection, report hashes, canonical/
Markdown/health consistency and a separate CLI process. It does not validate
live GPT or a regular-market session. Pytest uses `.pytest-tmp`, which is
ignored by Git and avoids stale system temp permissions on Windows.

### Quant V2 research-only reproduction

```powershell
.\.venv\Scripts\python.exe scripts/quant_diagnostic.py --output .tmp/quant-v2/new-diagnostic
.\.venv\Scripts\python.exe -m meridian quant inspect --dataset DATASET.json
.\.venv\Scripts\python.exe -m meridian quant backtest --dataset DATASET.json --plan PLAN.json --output .tmp/quant-v2/financial-oos
```

The diagnostic generates explicitly synthetic data and seals all 23 variants
before evaluating them. For an archived synthetic dataset, backtest additionally
requires `--diagnostic`. Financial evaluation rejects uncertified prices,
unknown corporate-action coverage, future availability and current-survivor
membership. This CLI never initializes the daily runtime. See
[research report](docs/quant-v2/RESEARCH_REPORT.md) for the complete saved registry,
mathematics, timing, costs, limitations and paper-review evidence gate.

## Layout and boundaries

- `src/meridian`: domain, pipeline, research, decision, paper and reporting code
- `tests`: deterministic unit, integration and regression coverage
- `scripts`: bounded diagnostics and validation entrypoints
- `policies`, `prompts`, `schemas`: packaged policy and contract inputs
- `docs`: architecture, operations and audit records

Meridian is paper-only. The canonical account is `Schwab-Paper`, broker
submission is always `DISABLED`, and GPT/Codex has no broker, order or ledger
authority. HSBC holdings are outside this system.

Paper runs serialize the complete lifecycle per account with an OS lock;
concurrent launches fail before research. SQLite transactions remain the final
duplicate-mutation guard. Corrupt lock metadata is preserved for inspection.
Canonical runtime writes and Doctor probes still require approved host execution.

## Windows and Linux

Core Python code uses `pathlib`, UTC-aware timestamps and argument-array
subprocesses. Windows launcher scripts are adapters around the same Python CLI;
Linux CI runs the identical validation entrypoint. Codex child processes are
started in an isolated process group so timeout cleanup covers descendants.

## Git workflow

Keep `main` stable and create `chore/*`, `fix/*`, or `feature/*` branches from
it. Do not force-push, rewrite history, enable a broker, or commit runtime data,
credentials, caches or `.env` files.

`.tmp/` and `dist/` are local generated artifacts, not source inputs. Historical
tracked artifacts were removed from the current tree without deleting local
copies or rewriting history; durable audit records remain in `docs/` and
`reports/`. Published audit documents use `<USER_HOME>` for personal paths.

## Quant V2.2 research-only challenger

Use project Python with `scripts/quant_v22_diagnostic.py --output .tmp/quant-v22/new-run`
for a new isolated synthetic registry. Replay the saved dataset/plan via the
Quant CLI; `quant packet` emits a research packet with no trade authority.
`scripts/validate_quant_v22_artifacts.py` verifies seven contracts, the current
archive and paired realized exposure. Full validation checks both this registry
and the preserved V2.1 archive. Exact V2.1 replay uses pinned commit 4664cb4.
Synthetic diagnostics never qualify financial evidence or promote a strategy.
