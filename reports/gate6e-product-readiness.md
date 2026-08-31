# Gate 6E product readiness matrix

Status: **SHADOW / NOT AUTHORIZED FOR ENTRY**

| Capability | Implemented | Real | PIT certified | Shadow | Executable | Tested | Blocker |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | --- |
| Account truth | TRUE | FALSE | FALSE | TRUE | FALSE | TRUE | real sanitized Host input required |
| Security identity | TRUE | TRUE | FALSE | TRUE | FALSE | TRUE | historical intervals remain bounded |
| Market | TRUE | TRUE | FALSE | TRUE | FALSE | TRUE | execution-grade provider not certified |
| Fundamentals | TRUE | TRUE | TRUE | TRUE | FALSE | TRUE | none for covered issuers |
| LLM | TRUE | TRUE | TRUE | TRUE | FALSE | TRUE | research alpha only |
| Dislocation | TRUE | FALSE | TRUE | TRUE | FALSE | TRUE | bounded shadow analysis |
| Quote | TRUE | FALSE | FALSE | FALSE | FALSE | TRUE | TO_BE_SELECTED/certificate absent |
| Manual ticket | TRUE | FALSE | FALSE | TRUE | FALSE | TRUE | Host and quote gates |
| Host | TRUE | FALSE | FALSE | TRUE | FALSE | TRUE | no externally authorized envelope |
| Replay | TRUE | FALSE | TRUE | TRUE | FALSE | TRUE | none |
| FinRL-X | TRUE | FALSE | FALSE | FALSE | FALSE | TRUE | MODEL_UNAVAILABLE |
| Broker | FALSE | FALSE | FALSE | FALSE | FALSE | TRUE | permanent product boundary |

Profiles: `TEST`, `REPLAY`, `SHADOW_LIVE`, `MANUAL_DECISION_SUPPORT`. `AUTO_EXECUTION` is not defined.

No broker writes, real orders, Schwab authentication, or automatic FinRL-X promotion are present.
