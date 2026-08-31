# Shadow V1 acceptance policy

Before any small-capital manual use, a human must review at least **5 completed
US trading sessions**; 10 is preferred. This period validates operations, not
investment performance.

Every session must preserve:

- no P0 and no readiness bypass;
- stable `meridian daily` execution and append-only ledger writes;
- green account/reconciliation invariants;
- explicit provider failures and quote freshness;
- stable evidence IDs/citations for certified research;
- no assumed fill: only a later Host snapshot changes brokerage truth.

A failed or incomplete session does not count. Performance statistics from a
small sample are labelled `INSUFFICIENT_SAMPLE` and are not used for promotion.
