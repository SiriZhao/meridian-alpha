# ChatGPT integration test

The local MCP server was smoke-tested with the installed Python MCP SDK:

- `/health` returned 200 and declares `execution_capability: false`.
- `/mcp` completed a streamable-MCP `initialize` request with HTTP 200.
- Tool registration includes `validate_account_snapshot`,
  `run_daily_analysis`, `get_run`, `get_order_ticket`, and `explain_decision`.
- No brokerage execution tool is registered.

Developer Mode and a public HTTPS tunnel were not connected in this unattended
local run. Before connection, use a stable HTTPS endpoint ending in `/mcp`, then
verify discovery and a fail-closed account-unavailable scenario.

References: [MCP quickstart](https://developers.openai.com/apps-sdk/quickstart),
[MCP server guide](https://developers.openai.com/apps-sdk/build/mcp-server), and
[tool planning](https://developers.openai.com/apps-sdk/plan/tools).
