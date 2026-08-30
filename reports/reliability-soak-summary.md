# Reliability soak summary

Result: `PASS` (`OFFLINE_REPLAY_SAFETY`)

The soak exercised fresh, stale, partial, duplicate, and externally changed
account states; market/SEC/DeepSeek/news/macro/provider failures; invalid,
neutral, bullish, bearish, and abstaining research outputs; future and stale
observations; restatements; dislocation disagreements; symbol mismatches; and
FinRL-X unavailable/bad-artifact cases. Every case stayed explicit and
fail-closed. No error was silently converted into a neutral research signal,
account truth, order, or broker action.

| Invariant | Result |
| --- | --- |
| Cash/holdings projection safety | PASS |
| Weight and research modifier bounds | PASS |
| Future/uncertified evidence cannot authorize | PASS |
| Certified signal required for research alpha | PASS |
| Quote required for manual readiness | PASS |
| Broker write surface absent | PASS |

External calls: `0`; broker calls: `0`; retries: `0`. Offline latency and cache
hit-rate measurements were not collected, so they remain explicitly
`NOT_MEASURED_OFFLINE`. FinRL-X remains `MODEL_UNAVAILABLE` and unpromoted.
