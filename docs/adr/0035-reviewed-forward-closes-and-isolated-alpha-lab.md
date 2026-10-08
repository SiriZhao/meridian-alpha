# ADR 0035: Reviewed forward closes and isolated alpha research

Status: implemented research boundary; financial alpha remains unverified.
Date: 2026-10-08. Extends ADR 0032–0034; no production policy changes.

## Decision

Public historical downloads, even fresh and date-aligned, are not verified
return evidence by provider reputation. `DatedClose` records a defined unadjusted
session close, USD currency, source, publication availability, ingestion time,
origin and adjustment status. The reviewed calendar scope is 2026–2028; older
unplanned exchange closures are not claimed to be covered by the generic
calendar. No execution-feed certification is issued.

`ReviewedPricePair` binds an immutable prediction, aligned symbol/benchmark
closes, reviewed inception prices, action coverage and receipt digest. A human
review reference and review timestamp are explicit attestations, not an
authenticated identity or cryptographic signature. Public/synthetic inputs and
unknown adjustments cannot pass the financial qualification boundary.

Split/reverse-split ratios change inception share count. Cash/special dividends
are held as distributions, without reinvestment. Event order is chronological;
same-instant ambiguity, unresolved symbol changes, suspensions and delistings
block calculation. Review must cover the entire decision-to-maturity interval,
including asset and benchmark. Late publication is allowed only after receipt;
it cannot become information available to an earlier decision.

New ingestion writes only explicitly isolated `alpha-lab/*.json` ledgers through
existing OS locks and atomic/fsynced writes. The complete reviewed receipt is
embedded in each outcome and revalidated against the frozen prediction on
reload. Retries preserve the original review time and outcome identity.
Canonical runtime/ledger/report writes are outside this adapter's authority.

Legacy v1/v2 records remain readable. Their existing date-aligned sample count
is preserved as compatibility telemetry and is separately labelled from
`reviewed_financial_sample_count`. Neither count proves sample independence or
positive alpha. Historical `QUANT_PLUS_LLM` labels with a null LLM score mean
advisory participation, not measured LLM influence; immutable records are not
rewritten to create a comparison cohort.

`alpha_lab` evaluates fixed cash, exact positive-daily-return operational,
21-session multi-factor and certified-research challengers. It imports no order
planner or broker interface. Only the existing evidence authorization type can
contribute research; no model is invoked. Fixed recipes are not selected from
outcomes. Missing/irregular/unknown-adjustment history refuses multi-factor
scores. Research confidence is not an upward-move probability.

Paired signal evaluation requires an ex-ante fixed universe and experiment
registration time, consistent horizon/benchmark, frozen baseline score match,
reviewed outcomes and complete common cross-sections. Overlapping intervals are
purged deterministically. Descriptive rank correlation and directional accuracy
are signal metrics, not executable portfolio returns or statistical proof of
alpha. Portfolio costs, drawdown and confidence intervals remain unavailable
until an audited execution/portfolio model and sufficient temporal data exist.

Production decision attribution records actual quant/allocation/risk/order
branches. Canonical state retains it once; Markdown, health and CLI serialize
that state. No research output changes operational sizing or policy.

## Validation and limitations

Synthetic fixtures validate contracts, immutable retry, corrupt input rejection,
process contention, corporate actions, holiday/DST and report projections.
They provide zero real financial samples. Human review is still required for
real close/action ingestion; no automatic public-feed verification is added.
All promotion and broker submission remain disabled.

The supported calendar scope was checked against the exchange's published
[2026–2028 calendar](https://ir.theice.com/press/news-details/2025/NYSE-Group-Announces-2026-2027-and-2028-Holiday-and-Early-Closings-Calendar/default.aspx).
Distributions without reinvestment must not be called an index total-return
series; see the [S&P index mathematics methodology](https://www.spglobal.com/spdji/en/methodology/article/index-mathematics-methodology/).
