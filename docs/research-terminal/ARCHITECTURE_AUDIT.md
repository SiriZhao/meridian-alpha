# Research terminal architecture audit — v1

Recovery base: `f2d06396268af9ba560f839a82012aa693fe60c0`, child branch
`codex/research-terminal`. The clean Quant worktree is separate from the root
Forward Evidence branch. PR #5 remains open against `codex/quant-live-bridge`.
Python 3.12 and the existing frozen environment are retained.

| Capability | Status at recovery | Actual implementation / gap |
|---|---|---|
| PIT features, attribution, regimes | IMPLEMENTED | `quant/features.py`, `signals.py`, `regime.py`; preserve missing-factor penalties and unknown confidence |
| Constrained challenger | IMPLEMENTED | `quant/portfolio.py`, `packet.build_research_packet`; existing risk, reconciliation, planner and projected validator remain authoritative |
| Real financial alpha evidence | BLOCKED_BY_DATA | Frozen synthetic registries in `quant/experiments.py` are engineering diagnostics; no independently qualified financial OOS claim |
| Public live research | IMPLEMENTED | `live_quant_bridge.build_live_quant_snapshot` preserves strict/provisional lanes; raw public history does not yield verified multi-session returns |
| Numerical MCP | LEGACY | `mcp_server.quant_metrics` uses caller dictionaries and older derived features; it does not expose the V2.2 factor engine |
| Evidence graph | IMPLEMENTED | `evidence_graph.EvidenceGraph.references_resolve` rejects dangling references, cycles and unresolved contradictions; numerical correspondence is not validated |
| Four native GPT roles | PARTIAL | `gpt_native_research.GPTNativeResearchOrchestrator._validated` checks schema/IDs; citing a valid ID does not itself establish numerical truth; subjective probabilities remain uncalibrated |
| MCP runtime read-only boundary | PARTIAL | `runtime_status` calls `report(probe_writes=False)` but report still creates directories; `_store` uses writable AuditStore; `market_snapshot` constructs cache/health writers |
| SEC/event/macro evidence | IMPLEMENTED | `company_facts` uses exact accession/availability certification; default SEC cache is disabled. Events/macros retain independent timestamps; source text is untrusted |
| Forward outcomes | IMPLEMENTED | `forward_evidence` calls existing `ForwardLedger.evaluate`; construction/evaluation do not append outcomes. Dependence/eligibility restrictions remain |
| Portfolio review | PARTIAL | `portfolio_context`/`risk_analysis` inspect in-memory account; no bounded weight-only what-if or declared scenario comparison |
| Planner | PARTIAL | `research_agents/preparation.py` handles bounded evidence acquisition; missing deterministic Quant view memoization and terminal-specific allowlist |
| Operator terminal | MISSING | Live Markdown exists in `live_report.py`; no single read-only view grouping market, factors, risk, GPT, decisions, experiments and health |
| Skill | PARTIAL | Existing `skills/meridian-alpha/SKILL.md` is evidence-first and preserves host approval; missing versioned, tool-bound workflow/output/budget contract |
| Intelligence tools | LEGACY | `intelligence_tools.dip_scout` uses the disabled provider; do not turn it into a second numerical engine |
| Canonical V1 and paper | IMPLEMENTED | `daily_closure.py`, `application.py`; unchanged default, no promotion, no database reset or broker capability |

Implementation priority: enforce actual read-only behavior; expose one bounded
Quant terminal snapshot rather than cosmetic factor/rank/regime aliases; add
isolated portfolio what-if with explicit shocks; connect these deterministic
records to existing native evidence validation and a compact Python terminal.
No coefficients, certification rules, risk limits or archived experiments change.

Acceptance limitations from Mission 3 remain: insufficient verified adjusted
history, unknown ETF look-through, uncalibrated expected returns/probabilities,
and external operator action for full native live acceptance. Engineering tests
cannot resolve these financial or host evidence blockers.

## Delivered capability map

| Capability | Status | Concrete integration / remaining boundary |
|---|---|---|
| Quant MCP research | IMPLEMENTED | `research_terminal.quant_terminal_snapshot` calls the existing `build_research_packet`; three typed MCP tools expose factors, rankings, regime, targets and lineage |
| Portfolio what-if | IMPLEMENTED | `portfolio_what_if` validates a sanctioned in-memory account, applies existing RiskEngine and calculates declared shocks; no order or ledger path |
| Native Quant evidence | IMPLEMENTED | `terminal_model_context` / `review_terminal` bind the numerical view to the existing four-role native chain; parser checks exact numerical citations and nested timestamps |
| Decision brief | IMPLEMENTED | `generate_decision_brief` separates facts, Quant, GPT, conditional prose, constraints, unknowns and possible action; stale prices and speculative probabilities are withheld |
| Terminal | IMPLEMENTED | `meridian terminal` prints seven read-only Chinese views or full JSON from an explicit bounded history request; no canonical application initialization |
| Read-only storage / cache | IMPLEMENTED | Guarded SQLite mode=ro refuses journal review, missing paths remain absent; MCP provider cache/health writes and runtime write/subprocess probes are disabled |
| Memoization / planner | PARTIAL | Fixed bounded Quant planner and 13 typed workflow plans with freshness/hash-bound receipt reuse; not a general autonomous concurrent provider/model planner |
| Observability | PARTIAL | Quant/risk/report timing, memoization, shared model invocation accounting and quality scorecard; real provider/model cost and controlled review-time improvement remain unmeasured |
| Skill instruction contract | IMPLEMENTED | Thirteen workflows ship typed tool allowlists, evidence, missing-data, risk, output, time/call and no-side-effect boundaries; compatibility Skill archive filename remains v1 |
| Experiment / forward tools | IMPLEMENTED | Existing frozen registries, inspection CLI and matured forward evaluation reused; no duplicate registry or outcome store |
| Real alpha / fundamentals / ETF overlap | BLOCKED_BY_DATA | No new qualified OOS data, authenticated history, calibrated expected return or look-through source introduced |
| Legacy compatibility diagnostics | LEGACY | `quant_metrics` and disabled intelligence-provider helpers retain their old meaning; they are not relabelled as V2.2 |

OS read-only permission remains the enforcement boundary against concurrent
SQLite journal-mode reconfiguration; application guards do not replace it.
All integration acceptance is engineering-fixture evidence, not actual live
provider/model acceptance or financial outperformance.
