# Shadow observation runbook

Use the durable ledger under `var/shadow/` and the reports under `reports/`.
Each run is append-only and identified by a run ID plus decision cutoff. The
performance ledger records the simulated execution assumption (normally
`NEXT_SESSION_OPEN`) and leaves future outcomes pending until the relevant market
observation is available.

Run the cache/replay battery and bounded offline soak before interpreting a new
observation. Track quant-only versus quant-plus-certified-research attribution
with the same allocator and risk engine. Keep dislocation attribution separate.
No result is a causal claim from a small sample, and no recommendation implies a
trade occurred.
