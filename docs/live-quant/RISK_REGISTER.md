# Quant live bridge — evidence blockers and recovery

| Risk / blocker | Meaning and recovery |
|---|---|
| INSUFFICIENT_VERIFIED_HISTORY | Obtain genuine PIT-adjusted/action-qualified bars; never relabel public records |
| Corporate actions UNKNOWN | Cross-session returns/current price basis may be invalid; provide reviewed coverage |
| Feed delay UNKNOWN / STALE | Retrieve new timestamped data; last reference stays dated, never current |
| Quotes UNCERTIFIED | Independent certified execution data and manual review required |
| Expected return UNCALIBRATED | Score is not win probability; require independent mature calibration |
| Sector / ETF overlap UNKNOWN | Supply source-backed metadata; no ticker-based guessing |
| Model login only | One bounded actual call needed; report quota/auth/model failure, no endless retries |
| Model failed/incomplete | Keep sealed Quant data, inspect exact stage error and retry independently |
| Account/schema missing | Preserve storage/history; explicit separate repair, never reset or auto-init |
| Ledger changed | Obtain new observation; never infer fills from recommendations |
| Stale root/MCP checkout | Use explicit active launcher; separately used MCP requires checked origin/restart |
| Skill hash mismatch INFO | Review/install separately; no automatic skill synchronization claim |
| Regular acceptance pending | Two independent qualified cycles; no forced time/session or fixtures |
| Real-alpha evidence pending | Genuine financial OOS and comparable exposure remain Mission 1 blockers |

Actual 2026-10-08 observations: Doctor/account/login/locking passed, but SPY was
91.16 seconds old during the full-universe research snapshot. Its stale state
blocked all model inference. Preserve the 90-second gate; retry only after a new
qualifying observation. Login READY remains distinct from proven model inference.
The original report's GPT FAILED label was a status defect: its stages were all
NOT_RUN and research state RESEARCH_BLOCKED_DATA. The corrected bridge emits
BLOCKED_DATA and model_inference_attempted=false; original immutable evidence is
preserved. Independent repeated regular-session acceptance remains pending.

GO means a defined research workflow can run, never trade authorization.
WAIT_FOR_EVIDENCE may be the correct entire report. No news, value, entry price,
account envelope or ranking is invented to show activity. Existing canonical V1
constraints and per-order manual authority remain mandatory.
