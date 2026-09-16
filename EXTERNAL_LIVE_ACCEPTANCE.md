# Meridian external live GPT acceptance

This harness must be run from a normal Windows Terminal / PowerShell session, outside the Codex developer terminal. It is shadow-only and cannot create or execute orders.

```powershell
cd "E:\CSDIY\Vibe Coding Project\meridian-alpha"
.\scripts\verify_live_gpt_external.ps1 -MarketFixturePath .\path\to\multi_symbol_market_fixture.json
```

The fixture should contain the intended frozen/current structured market quotes (preferably AAPL, MSFT, NVDA, and SPY). Do not invent prices or copy credentials into the repository. An optional `-MarketFixturePath2` supplies a second symbol set for the second shadow run.

The script first rejects a PowerShell process with a Codex ancestor. It then performs a bounded direct Codex model request (B). If B fails, it stops without role or chain calls and writes `external_live_acceptance.json` under `.tmp\external-acceptance\<timestamp>\` with `P1_STAGE2_EXTERNAL_CODEX_BLOCKED`.

Only when B succeeds does it run the four real Meridian roles individually, followed by two full shadow runs. Every artifact records sanitized statuses and keeps `shadow_only=true`, `orders_created=0`, `orders_executed=0`, and `execution_authority=NONE`.

Return the printed `RESULT FILE:` JSON to the Meridian task for verification. The JSON contains no raw prompts, credentials, tokens, cookies, or unbounded provider output.