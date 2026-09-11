# Meridian Astra final maintainer review

**FINAL STATUS: BLOCKED_WITH_EVIDENCE**  
Review date: 2026-09-11. Production research acceptance has **not** passed.

Source engineering and real clean installation pass. The single fresh GPT-6 Astra session returned `CODEX_RATE_LIMITED` before any Skill read or MCP call. SEC returned HTTP 403; the pre-market public quote was stale. No retry, substitute model, fabricated result or execution authority was introduced.

## Repository and checkpoint

- Starting branch: `astra/canonical-production-workflow`; starting commit: `3f6bdac`.
- Inherited implementation checkpoint: `ef90bd0` (82 files).
- Repair commits: `3fbfe0f`, `fd358330003d2ff6413c3b63b0aaf3263554f15c`.
- Ending accepted implementation: `fd358330003d2ff6413c3b63b0aaf3263554f15c` on `astra/canonical-production-workflow`. The later report-only commit is identified by the final handoff and `git log -1 -- reports/meridian-astra-final-review.md`; it does not change the tested code.
- Reviewed prior evidence commits: `3f6bdac`, `066e09f`, `72b6d46`, `0b55cde`, `db36ff2`, plus implementation context at `7a7eff5`.
- Preserved the unrelated modified `reports/gate6g-quote-preflight.json` and pre-existing `.acceptance-dist*` directories. No remote push or release tag.

## Repairs

There are **24 confirmed repair groups**, with 22 new regression cases. This is not a claim that arbitrary unseen inputs are defect-free.

| ID | Defect | Repair |
| --- | --- | --- |
| D01 | Result cutoff bypass | Validate every evidence timestamp against the result cutoff, not only the evidence-local cutoff. |
| D02 | Result identity, type and authority spoofing | Reject duplicate evidence IDs, claim-section mismatch and unsupported confidence; constrain authority to NONE. |
| D03 | Decorative graph validation | Reject cycles, duplicate edges, mistyped support edges, unsupported confident claims and unacknowledged contradictions. |
| D04 | Incorrect YTD and opening gap | Use the prior-year close for YTD and current open versus prior close for gap. |
| D05 | Partial histories mislabeled as full windows | Require complete volatility/volume/relative-performance/beta windows; use high/low extrema for 252-session distances. |
| D06 | SEC filing label/context confusion | Classify by duration rather than filing FY label and resolve the dei shares-outstanding concept. |
| D07 | Incorrect YoY/current fact selection | Bound annual comparables to 330–400 days and make period/availability outrank concept precedence. |
| D08 | Debt double counting and lost components | Deduplicate a coherent debt pair from one accession; reject incomplete/conflicting pairs and retain component IDs/records. |
| D09 | Missing quarterly and TTM context | Expose bounded quarterly history and derive QoQ/TTM only for compatible consecutive reported quarters. |
| D10 | Packet reference and cutoff gaps | Reject packet-level future evidence, duplicate IDs and unresolved conflict IDs. |
| D11 | Fundamentals erased by OHLCV compaction | Compact only historical price/volume/benchmark arrays and preserve raw source references. |
| D12 | SEC retrieval bypassed acceptance certification | Route the numerical retrieval adapter through the same certified snapshot service as company_facts. |
| D13 | Tool receipt time presented as known-at | Report receipt separately; leave unavailable known-at null and provide certified SEC acceptance time where known. |
| D14 | Unvalidated bars claimed source provenance | Reject malformed/nonfinite/duplicate/impossible bars, sort before reporting and mark supplied inputs unverified. |
| D15 | Account freshness/risk wrapper gaps | Check elapsed account age against configured policy and reject stale/future risk inputs. |
| D16 | Event duplicates and macro temporal conflicts | Deduplicate bounded events, disclose exclusions and reject future macro release/period or equal-time numerical conflict. |
| D17 | Nested writing daily path exposed as read-only | Remove two legacy daily functions from MCP registration while preserving Python compatibility and explicit CLI operation. |
| D18 | Research packet could not retrieve by subject | Extend the existing tool to compose a bounded deterministic symbol/cutoff packet. |
| D19 | Provider and quality fail-closed gaps | Preserve malformed-provider errors, reject post-cutoff results and evaluate expiry against the analysis time. |
| D20 | Benchmark identity, units and lineage errors | Do not substitute QQQ for SPY; pass QQQ separately, retain benchmark IDs and label price/volume/oscillator units correctly. |
| D21 | Live historical receipt clock defect | Bind live collection time after history receipt; replay retains its immutable cutoff. |
| D22 | Intraday return used two-session-old close | Use latest completed close for a current-session quote; keep opening gap unknown without that session open. |
| D23 | SEC timezone inference and hidden HTTP failure | Reject timezone-less acceptance data before conversion and preserve HTTP status in identity failure diagnostics. |
| D24 | Installed Skill required checkout-relative launcher | Document installed CLI operation and tool provenance/packet behavior; synchronize the canonical Skill. |

## Architecture and documentation

ACTIVE: Astra performs synthesis through the installed Skill and deterministic read-only tools. LEGACY: the separately operated daily/paper CLI and isolated provider adapters. HISTORICAL: earlier Gate/DeepSeek/TradingAgents reports. TEST-ONLY: synthetic/replay fixtures. No PAT or brokerage execution path was added.

ADR 0020 records removal of two legacy daily functions from MCP registration. Final registration has 26 structured, read-only tools; the old install report's count of 29 was not current runtime truth. Old reports also did not establish fresh-host research completion. Canonical README, architecture, build-state pointers and operator instructions now distinguish installation health, research availability, manual readiness and paper simulation.

## Validation

- Baseline: 449 tests passed.
- Final: **471 passed, 0 failed**, 63.72 seconds; 22 new regression cases in `tests/test_final_acceptance_regressions.py`.
- Ruff: PASS. Pyright: PASS, 0 errors and 0 warnings.
- Source `pip check`: PASS. Clean `uv pip check`: PASS, 41 compatible packages.
- Compile/import smoke: PASS. Source and clean doctor: PASS. DB schema: 3.
- Existing Hatchling wheel build: PASS. Source-to-wheel Python byte comparison: PASS. No runtime DB or environment files in wheel.

The Skill was synchronized before the final full test run. An intermediate full run correctly failed doctor while source/install Skill hashes differed; synchronization resolved that installation condition without weakening doctor.

## Real installation and MCP

Wheel SHA-256: `5be3901d2472a476021ca034cf824fa73ffa4f438bfacbf657f4e5f1ec2a8636`. Fresh environment: `E:\Meridian Final Acceptance 20260911\venv-final`. Outside-checkout workdir: `E:\Meridian Final Acceptance 20260911\外部 工作目录`. The wheel uses packaged policies and writable RuntimePaths, not checkout writes. Init/re-init, synthetic report generation, immutable audit persistence, DB integrity, CLI restart and stdio startup all passed. Synthetic execution is explicitly not live research proof.

Skill file count: 10. Source hash: `ddc1dc3c2ac6d430a4244f0702836b9bde3f5286cbf0f7c57cf971d8994af9aa`. Installed hash: `ddc1dc3c2ac6d430a4244f0702836b9bde3f5286cbf0f7c57cf971d8994af9aa`. Packaged Skill hash matches too.

Actual registered tools:

`validate_account_snapshot, validate_host_account_snapshot, get_provider_health, get_run, get_daily_report, inspect_evidence, inspect_research, inspect_target_portfolio, inspect_portfolio_target, inspect_manual_draft, provider_health, get_order_ticket, explain_decision, runtime_status, market_snapshot, account_snapshot, company_facts, event_evidence, macro_context, research_packet, quant_metrics, portfolio_context, risk_analysis, forward_evidence, daily_closure, audit_lookup`

The exact saved Codex server command and a separate clean-wheel server both completed initialize/list-tools and calls to runtime_status, market_snapshot, company_facts, quant_metrics and research_packet. Every tested response retained `execution_authority=NONE`. Runtime passed; market returned stale context with a blocking diagnostic; company facts returned SEC HTTP 403; empty quant input was rejected. A separate real stdio synthetic arithmetic call returned 0.1 for 100 to 110. Transport success does not mean live research availability.

## Actual fresh Astra evidence and quality

- One session: `01a090a1-cb92-7702-963e-6520e896b9f0`.
- Requested model: `gpt-6-astra`, provider `openai`, reasoning `medium`.
- Empty fresh working directory; no repository preload; exact user-specified GOOGL prompt.
- CLI exit: 1. Actual error: "You've hit your usage limit."
- No model inference, Skill file read, MCP call, evidence citation or completed company research was observed. Model execution is not claimed merely because the requested model was supplied on the command line.
- COMPANY_RESEARCH, NEWS_IMPACT/EARNINGS_REVIEW and PORTFOLIO_REVIEW model acceptance remain unverified. Same-session followups and fresh-model restart were stopped under the quota rule.
- Research-quality status: **NOT_EVALUATED**. There is no model output against which to certify factual correctness, contradiction discovery, citation resolution or absence of unsupported claims.

The raw local event file is outside Git; its path and SHA-256 are in the JSON report. No credentials, account identifiers, DBs, caches or raw logs are committed.

## Adversarial and restart acceptance

- missing_market_data: PASS: empty-bar rejection and missing-provider regressions.
- stale_market_data: PASS: real GOOGL quote remains STALE / MARKET_DATA_STALE.
- future_market_data: PASS: test_operational_market_snapshot and cutoff regressions.
- provider_timeout: PASS: provider adapter and final regression tests.
- provider_malformed_response: PASS: final ValueError/TypeError regressions preserve failures.
- provider_disagreement: PASS: test_source_conflict and operational quote conflict tests.
- missing_historical_data: PASS: incomplete-window metrics remain null and empty input is rejected.
- missing_fundamental_field: PASS: existing numeric tests and certified empty snapshot regression.
- future_SEC_filing: PASS: test_sec_filing_metadata and test_fundamentals.
- duplicated_fundamental_facts: PASS: debt duplicate regression; component lineage retained.
- conflicting_numerical_sources: PASS: test_source_conflict.
- unavailable_news_provider: PASS: missing evidence remains explicit; no autonomous live feed is claimed.
- unavailable_macro_provider: PASS: empty macro tool returns MACRO_CONTEXT_MISSING.
- malformed_evidence: PASS: schema and graph regressions.
- unknown_evidence_ID: PASS: test_astra_foundation and test_evidence_graph.
- contradictory_evidence: PASS at contract level; model contradiction quality NOT_EVALUATED.
- insufficient_evidence: PASS at schema/provider level; real model synthesis NOT_RUN.
- stale_account_snapshot: PASS: age and freshness regressions.
- future_account_snapshot: PASS: account and risk regressions.
- MCP_unavailable: NOT_INJECTED in real Astra host; stdio availability/reconnection actually passed.
- Codex_unavailable: PASS: test_executable_missing_is_explicit_and_not_retried.
- Codex_quota_limited: PASS: real fresh session failed explicitly; no retry or substitute model.

Both clean and configured MCP processes exited and new processes initialized successfully. CLI restart preserved runtime paths and healthy schema 3. Skill hashes persisted. This was process restart, not a literal OS reboot, and no quota-consuming second Astra session was run.

## Remaining limitations

- Fresh Astra discovery, tool selection, full company research, citation resolution and substantive research quality remain unverified because the only session was quota-limited.
- SEC ticker retrieval returned HTTP 403; certified live GOOGL fundamentals could not be evaluated. No alternative values or identity were invented.
- Pre-market GOOGL last-session public quote remained stale. Stooq returned HTTP 404. Neither source is execution-grade.
- News and macro MCP tools accept source-bound input; this is not a verified comprehensive live news/macro feed. The symbol packet explicitly leaves those unknown.
- Quarterly/TTM coverage requires reported compatible consecutive quarters. Missing quarter extraction, forward estimates and valid valuation inputs are not fabricated.
- Public historical corporate-action adjustments and information-event PIT certification remain unverified. 52-week distances use a 252-session proxy; RSI/ATR retain the existing rolling-average formulas.
- Evidence contracts check structure/identity/timing, not the semantic truth of arbitrary source prose. Model-level unsupported-claim and contradiction acceptance is NOT_EVALUATED.
- No literal OS reboot or second Astra session was run; CLI/MCP process restart and DB/Skill disk persistence were verified. Fresh-model rediscovery after restart is blocked by the quota rule.
- Current Codex MCP registration still points to the project Python environment. That exact configuration and a separately installed wheel server were both tested; no configuration or credentials were migrated.

## Next action

After quota is available and SEC access is restored, run one fresh medium-effort Astra company research acceptance, bounded same-session followups and minimal rediscovery. Do not label production-ready before reviewing real evidence and citations.

The companion JSON includes exact artifact hashes, tool statuses, file changes, repair inventory and evidence locations.
