# Chinese decision research workflow

Use the active worktree and its Python 3.12 frozen environment. GitHub changes
do not update another checkout's interpreter/import automatically.

```powershell
Set-Location 'E:\CSDIY\Vibe Coding Project\meridian-alpha\.worktrees\flagship-quant-20261009'
.venv\Scripts\python.exe -c "import meridian; print(meridian.__file__)"
.venv\Scripts\python.exe -m meridian terminal C:\Inputs\quant.json --engine V2.3_SHADOW --research-input C:\Inputs\research.json --json
```

quant.json is QuantTerminalRequest with shared analysis_cutoff, qualified
histories, explicit metadata and engine. research.json is DailyResearchInput
with actual observation timestamps, quote references and provider_provenance.
JSON source contracts are in schemas/research-terminal.v1.schema.json.
Missing history produces a bounded blocked report with required inputs, not
fabricated scores. Public research cannot be certified by a command flag.

Without --json the same workflow prints concise Chinese Markdown. Adding
--gpt explicitly invokes the existing bounded native chain using checked-in
model policy. Model failures are displayed; deterministic research survives.
Real model/host acceptance must use the documented external-terminal boundary
when the harness requires it. Successful fixture calls are not live results.

Optional --paper-review C:\Inputs\paper-review.json accepts PaperReviewRequest
with the identical Quant request, an explicitly supplied sanitized authorized
Schwab-Paper account, certified ExecutionQuote/capability objects and matching
planner MarketSnapshot inputs. It computes isolated PAPER_ONLY drafts, never
fills or ledger entries. A research zone is never used as an executable limit.
Missing account, stale price, session/certification/risk failure has named
blockers. Raw account values are not persisted by this stdout workflow.

For the existing live observation workflow:

```powershell
.\scripts\run_live_advisory.ps1 -Account Schwab-Paper -QuantEngine V2.3_SHADOW
```

The launcher now defaults to V2.3_SHADOW research; V2.2_SHADOW explicitly rolls
back the research comparison. Canonical V1 paper operations are unchanged.
This launcher writes reports/cache: if canonical runtime is selected, approved
host execution is required before invoking it. This development acceptance did
not run it on the canonical host or prove regular-session acceptance.

Read-only MCP: quant_research_snapshot supports engine selection;
decision_research_brief returns attribution, conditions and unknowns without
a model call; research_paper_plan accepts explicit paper inputs for gated
non-executing planning. All have bounded typed input/output schemas.

Reproduce the shipped engineering example:

```powershell
.venv\Scripts\python.exe scripts/decision_report_example.py
.venv\Scripts\python.exe -m pytest tests/test_research_decisions.py -q
```

sample-fixture-report.md and golden-decision.json are SYNTHETIC_DIAGNOSTIC,
not today's prices or actual investment recommendations. No new strategy
returns are claimed: this change connects research to users, not new OOS alpha.
