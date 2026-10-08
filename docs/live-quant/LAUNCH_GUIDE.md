# Mission 2 — verified active-checkout launch guide

Use `E:\CSDIY\Vibe Coding Project\meridian-alpha\.worktrees\quant-engine-v2`,
branch `codex/quant-live-bridge`, child of Mission 1's exact `69eb57a`.
The root checkout remains the Forward Evidence foundation. Updating GitHub does
not change that launcher or an already running MCP process. Do not merge PRs
to change the runtime. Use this checkout's Python 3.12.10 and frozen 48 packages.

The launcher asserts imports originate under this checkout's `src`, and prints
the loaded policy directory. Inspect/clear an unintended MERIDIAN_POLICY_DIR
override deliberately; never silently copy policies. Quant default remains
quant-v2.1 / QUANT_V1_BASELINE; quant-v22.yaml is SHADOW_ONLY. Research configured
provider/model/effort: codex_cli / gpt-5.6-luna / low. Actual calls report their
effective route; login READY does not prove model availability or quota.

Canonical commands below require approved host execution in Codex before starting.
The script itself does not cross the sandbox boundary.

```powershell
Set-Location 'E:\CSDIY\Vibe Coding Project\meridian-alpha\.worktrees\quant-engine-v2'
.\scripts\run_live_advisory.ps1 -RuntimeHome 'E:\MeridianAlphaRuntime' -Readiness
```

Readiness performs Doctor, read-only account/schema/ownership inspection, the
canonical lock probe, one SPY observation per public provider and login preflight.
No model inference, account initialization, daily run, paper trade, reset or
migration occurs. DEGRADED exit 2 is intentional. Inspect the unique output_files.
The first dated preopen report is immutable; later checks use new subdirectories.

The real 2026-10-08 observation at 09:19 New York showed Doctor/account/login PASS,
Yahoo stale, Nasdaq fresh public reference, paper cash/book NAV 100000, no
positions and ledger version 0. That report discloses dirty development source;
it is not final-code or regular-session acceptance.

After regular open and fresh inputs qualify, use the single research workflow:

```powershell
.\scripts\run_live_advisory.ps1 -RuntimeHome 'E:\MeridianAlphaRuntime' -RoleTimeout 90 -ReasoningEffort low
```

It reads the existing ledger, seals Quant evidence before GPT, refreshes quotes
before final advice and creates new reports. It never executes paper/broker orders.
Model failure preserves packet, exclusions and Chinese wait explanations. Inspect
the saved report before any retry. Repeat only for the independent second
qualifying observation; no forced clock/session/date or fixture can qualify.
Formal acceptance still needs the separately required fresh account and two
independent cycles. Paper ledger read time is not broker observation time.

Canonical paper run remains a separate approved operational workflow with an
existing account and day ownership, not a bridge demo. Do not reset/auto-create it.

```powershell
.\.venv\Scripts\python.exe scripts/validate_repo.py
.\.venv\Scripts\python.exe scripts/live_bridge_fixture.py --output .tmp/live-bridge-fixture
```

The sample is synthetic, never today's market or financial OOS. See ADR 0039,
acceptance, checkpoint and risk register. Rollback retains V1/parent checkout
without any ledger operation. Final source/CI identities are recorded only after
execution.
