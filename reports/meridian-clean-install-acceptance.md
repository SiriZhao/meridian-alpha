# Meridian clean-install acceptance

**FINAL STATUS: BLOCKED_WITH_EVIDENCE**  
Installation substatus: **PASS**. Real Astra research substatus: **BLOCKED_WITH_EVIDENCE / CODEX_RATE_LIMITED**.

The actual final wheel was installed in a newly created Python 3.12 environment, separate from the project `.venv`. No mock substitutes were used for CLI or MCP transport. Synthetic data was used only for explicitly labeled report/audit and arithmetic tests.

| Check | Actual result |
| --- | --- |
| Starting commit | 3f6bdac |
| Ending accepted implementation | fd358330003d2ff6413c3b63b0aaf3263554f15c |
| Branch | astra/canonical-production-workflow |
| Build | Existing Hatchling configuration via uv build --wheel |
| Wheel SHA-256 | 5be3901d2472a476021ca034cf824fa73ffa4f438bfacbf657f4e5f1ec2a8636 |
| Wheel contents | 122 files; no DB/environment files; all source Python bytes match |
| Fresh environment | E:\Meridian Final Acceptance 20260911\venv-final |
| Interpreter | E:\Meridian Final Acceptance 20260911\venv-final\Scripts\python.exe |
| Outside-checkout workdir | E:\Meridian Final Acceptance 20260911\外部 工作目录 |
| Runtime home | E:\Meridian Final Acceptance 20260911\runtime-final |
| Policy loading | Packaged policies in site-packages; PASS |
| CLI/import | PASS |
| Init and idempotent migration | PASS; schema 3 |
| Doctor | PASS |
| Dependency integrity | PASS; 41 compatible packages |
| Report writing | PASS; synthetic daily, research NOT_RUN |
| Immutable research audit | PASS; UNKNOWN-only test result |
| Database integrity | ok |
| Skill tree | 10 files, exact source/install/package equality |
| MCP | Real stdio initialize/list/calls PASS; research data availability separately blocked |
| Process restart | CLI and both MCP launch paths PASS |
| Fresh Astra | One medium-effort requested gpt-6-astra session; CODEX_RATE_LIMITED |
| Execution authority | NONE |

Skill source and installed SHA-256: `ddc1dc3c2ac6d430a4244f0702836b9bde3f5286cbf0f7c57cf971d8994af9aa`.

Exact saved Codex MCP launch: `E:\CSDIY\Vibe Coding Project\meridian-alpha\.venv\Scripts\python.exe` with `-m meridian.mcp_server`. The configuration was inspected selectively and left unchanged. The independently installed wheel server was also started and tested. Mutable production state did not require checkout writes.

Required live calls were made to runtime_status, market_snapshot, company_facts, quant_metrics and research_packet. Runtime passed. GOOGL's last-session quote remained stale; SEC returned HTTP 403; empty quant input failed explicitly. A separate synthetic real-stdio calculation passed. These results must not be relabeled as a successful full company research.

The fresh session `01a090a1-cb92-7702-963e-6520e896b9f0` failed before any Skill read or MCP call. No further Astra session or followup was launched. Factual synthesis, citations, contradictions, portfolio reasoning and post-restart Skill rediscovery remain unverified. The process-restart check is not an OS reboot.

See `meridian-clean-install-acceptance.json` for paths, hashes, actual response statuses and evidence references, and `meridian-astra-final-review.md` for the 24 repair groups and remaining limitations. The later report-only commit does not change this tested implementation.
