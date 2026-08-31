# Manual order ticket

A ticket is a human review artifact, never an execution request. Production
construction requires a READY `ManualReadinessCertificate` (all seven gates)
and the exact `ExecutionQuote` plus matching capability certificate. Research
prices, valuation marks, LLM output, and quote-provider target quantities are
never sufficient. Show ticker, side, shares, deterministic limit, estimated
notional, weights, time in force, reasons, warnings, and recalculate
conditions. Always label it `NOT_EXECUTED`; never infer a fill from a draft.
