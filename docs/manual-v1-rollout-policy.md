# Manual V1 rollout policy (design only)

This document does not activate manual entry or connect a broker. If a future
human-approved rollout begins, use a small-capital phase with a strict maximum
notional, human review of every `ManualOrderDraft`, one-click-less entry, and a
daily reconciliation check.

Required prerequisites:

1. stable manual decision-support release;
2. real Host smoke passes;
3. certified ExecutionQuote capability and valid quote instance;
4. at least 5 (preferably 10) completed shadow sessions;
5. no P0 and stable reconciliation;
6. explicit user authorization for the future phase.

LLM output never supplies quantity, limit, TIF, or execution state. Drafts are
always `NOT_EXECUTED`; no broker API is part of this policy.
