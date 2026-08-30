# Execution quote provider decision

Status: **TO_BE_SELECTED**. This is research only; no provider is connected
through a broker or used for order submission.

| Candidate class | Bid/ask | Timestamp/freshness | Coverage | Authentication/cost | Current decision |
| --- | --- | --- | --- | --- | --- |
| Yahoo chart/quote | last-only | public response, delay/SLA not certified | stocks/ETFs, VIX symbol context | public terms/rate limits require review | shadow-only; not execution-grade |
| Licensed market-data vendor | evaluate contractually | require exchange timestamp and freshness SLA | US equities/ETFs/VIX | likely authenticated/paid | future evaluation |
| Exchange/CBOE-authorized feed | evaluate contractually | require explicit session/extended-hours semantics | venue-specific | licensing required | future evaluation |

A selection must demonstrate bid, ask, reliable timezone-aware timestamps,
freshness semantics, US stock/ETF/VIX support as needed, rate/reliability and
licensing review. Until then, `execution_quote_grade=false` and manual entry
remains blocked.