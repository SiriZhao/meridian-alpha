# Meridian Alpha — Gate 3B.4 Shadow Daily Run

## Run contract

The first daily run is an offline deterministic shadow exercise using a
sanitized synthetic `$50,000` cash-only `AccountSnapshot`. It uses TEST-mode
candidate selection, a bounded three-ticker graph budget, replay fundamentals,
news and macro fixtures, and a fake grounded normalizer. It does not contact
an account provider, market API, TradingAgents, DeepSeek, Schwab or a broker.

The pipeline is:

`AccountSnapshot → Security Master → Quant features → CandidateSelector →
ResearchPipelineService → graph summary → Meridian evidence packet → grounded
normalizer → certification boundary → Alpha Fusion/allocator/risk/reconciliation`

Synthetic evidence is intentionally not authorized. Consequently the run emits
zero `CertifiedAgentSignal` objects even when the fake normalizer returns an
explicit diagnostic outcome. Quant allocation remains deterministic and the
shadow report says **SHADOW / NOT AUTHORIZED FOR ENTRY**.

## Candidate diagnostics

The generated JSON and Markdown reports include, for every researched
candidate: quant-only score, grounded-research modifier, final alpha, evidence
completeness and sources, research direction/conviction when present, risk
penalty, target before risk and target after risk. Synthetic evidence quality
is zero, so no research modifier influences executable allocation.

The input universe contains five names while the research budget permits three.
Ordering is deterministic (quant score descending, ticker tie-break); deferred
names are listed explicitly with `BUDGET_LIMIT`. No whole-universe graph scan
is possible through this service.

## Failure behavior

Provider failures remain explicit per provider. Missing, future, stale,
conflicting or replay-unsafe evidence produces blocked/insufficient outcomes;
no neutral signal is fabricated. A live normalizer or graph provider cannot be
used in TEST mode because the service rejects network-capable providers before
invocation.

## Result

See `reports/gate3b4-shadow-daily.json` and
`reports/gate3b4-shadow-daily.md` for the sanitized run artifact. The run is
synthetic/replay-only and is not an authorization or order recommendation.

No live DeepSeek request, live TradingAgents request, Schwab connection,
FinRL-X call, broker call or real order was made.
