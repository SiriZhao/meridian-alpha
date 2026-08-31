# Meridian Alpha Skill runtime dependencies

The portable Skill package is intentionally instruction-led and MCP-independent.
Its preflight and wrapper scripts use only the Python standard library.

| Classification | Components | Purpose |
|---|---|---|
| REQUIRED | Python 3.12+; sanitized JSON input; a Host capable of supplying the input or a user-provided envelope | Run the portable preflight and safely describe or validate the workflow. No credentials are accepted. |
| OPTIONAL | An installed `meridian-alpha` project runtime and its pinned dependencies (`pydantic`, `PyYAML`, and the project’s MCP dependency) | Execute the proven deterministic core through `run_daily.py`; the wrapper delegates to the project CLI and never duplicates calculations. |
| OPTIONAL | Certified SEC evidence/cache, bounded market data, and a certified execution-quote capability | Enable corresponding production-path gates. Missing capabilities remain explicit blockers. |
| OPTIONAL | DeepSeek live transport | Add bounded certified research only when explicitly enabled. Replay/frozen outputs are preferred for historical runs. |
| OPTIONAL | MCP server | Web/desktop read-only integration only. The basic Skill workflow does not require localhost, developer mode, or MCP. |
| DEVELOPMENT_ONLY | Git, GitHub CLI, `uv`, pytest, Ruff, Pyright, full repository checkout, FinRL-X, TradingAgents vendor code, and broker/future-integration code | Build, test, package, and maintain Meridian; none is required to install the Skill. |

If the project runtime is absent, the wrapper reports
`MERIDIAN_RUNTIME_UNAVAILABLE` and does not reproduce Quant, AlphaFusion,
allocation, risk, reconciliation, or pricing in free-form prose. FinRL-X,
TradingAgents, live DeepSeek, and execution quotes are optional/deferred gates;
none is silently treated as available.