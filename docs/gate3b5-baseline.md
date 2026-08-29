# Gate 3B.5 Baseline

- Branch: `main`
- HEAD: `fb4850b03371cc8fc7d70723498bd736b2b3c51f`
- Python: `3.12.14`
- Worktree: contains the uncommitted Gate 3B.1–3B.4 implementation and
  documentation changes; no unrelated files were overwritten.

## Initial validation discrepancy

The first baseline run produced **132 passed, 7 failed**. All seven failures
were in `tests/test_tradingagents_adapter.py` and were caused by a fixed
2026-08-28 `AS_OF` being compared with the live wall clock, which caused the
production historical-live guard to reject the test request. This was a test
fixture defect, not a production safety defect.

The tests were changed to derive `AS_OF` from the current UTC clock (one minute
before collection) and to derive the expected graph trade date from that value.
The production `_live_as_of_within_tolerance` guard was not weakened. The
historical rejection test remains fixed by a one-second tolerance.

After this deterministic test repair, the TradingAgents adapter tests pass and
full validation is rerun in the Gate 3B.5 final report.
