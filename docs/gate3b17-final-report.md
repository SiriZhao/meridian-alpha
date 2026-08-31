# Meridian Alpha — Gate 3B.16 / 3B.17 Final Report

## Result

The first real numeric chain is complete for the bounded AAPL/NVDA/MSFT run:
SEC Company Facts numeric observations were joined to exact accession metadata
and SEC `acceptanceDateTime`, then converted into PIT-certified facts,
comparable series, derived metrics, bounded certified evidence, and shadow
research inputs. No broker, account, order, or execution path was used.

## Real certified fundamentals

| Ticker | Certified facts | Comparable series | Derived metrics | Latest accepted accession |
| --- | ---: | ---: | ---: | --- |
| AAPL | 429 | 12 | 16 | `0000320193-26-000020` at `2026-07-31T10:01:02Z` |
| NVDA | 334 | 11 | 14 | `0001045810-26-000075` at `2026-08-26T20:36:00Z` |
| MSFT | 436 | 12 | 18 | `0001193125-26-323660` at `2026-07-29T20:08:01Z` |

The report is bounded to the 12 most recent observed accessions per ticker for
network control, while each retained numeric observation preserves concept,
unit, period/context, form, filed date, accession, source hash, and retrieval
time. Missing or mismatched metadata is excluded; no filed-date midnight or
period-end timestamp is used as availability.

Derived values include revenue, gross profit, operating income, net income,
diluted EPS, cash-flow and balance-sheet YoY series, margins, and FCF where
period/unit compatibility is explicit. Quarter/YTD and unit mismatches remain
non-comparable. Later amendments cannot leak into an earlier cutoff.

## DeepSeek V3 shadow

Exactly three live calls were made after the enriched `CertifiedEvidenceView`
was built:

- AAPL: `AVAILABLE`, `BULLISH`, conviction `0.82`; authorized
  `CertifiedAgentSignal`; bounded base research modifier `+0.18` (cap).
- NVDA: `AVAILABLE`, `BULLISH`, conviction `0.95`; authorized
  `CertifiedAgentSignal`; bounded base research modifier `+0.18` (cap).
- MSFT: `ABSTAIN` because no certified evidence packet was available to the
  grounding boundary in that call.

The directional outputs were natural model responses; no prompt rule forced a
non-neutral stance. Shadow alpha effects are diagnostic only and remain
`SHADOW / NOT AUTHORIZED FOR ENTRY`.

## Dislocation V2

The deterministic bounded screen ran against real read-only Yahoo historical
shadow observations for AAPL/NVDA/MSFT and produced no eligible candidate in
this run. Certified dislocation assessments: `0`. Raw evidence cannot bypass
`CertifiedEvidenceView`, and the existing base/dislocation/combined modifier
caps remain enforced.

## Readiness

- Security Master authoritative: `0/11`; no enum-only promotion.
- Execution quote: `TO_BE_SELECTED`; Yahoo remains last-only research shadow.
- Manual entry: `NO` (quote authority and supervised account truth absent).
- Host: contract implemented; no real Host envelope supplied.
- FinRL-X: contract present; runtime/artifact `MODEL_UNAVAILABLE`; no promotion.
- News and macro: unverified/configuration-limited; excluded from certified
  grounding.

## Validation and artifacts

The full repository suite, Ruff, Pyright, and `git diff --check` are run at the
checkpoint. Generated artifacts:

- `reports/gate3b16-real-certified-fundamentals.json/.md`
- `reports/gate3b17-dislocation-shadow.json/.md`
- `reports/gate3b17-real-shadow-v8.json/.md`

Legitimate labels: `REAL_XBRL_CERTIFICATION_BREAKTHROUGH`,
`REAL_LLM_ALPHA_BREAKTHROUGH`, `CERTIFIED_FUNDAMENTAL_PIPELINE_READY`, and
`READY_FOR_LONGER_SHADOW_OBSERVATION`. `CERTIFIED_DISLOCATION_PIPELINE_READY`
is not claimed because no candidate was assessed.

Final stop: no Schwab, no broker writes, no real orders, no automatic
FinRL-X promotion.
