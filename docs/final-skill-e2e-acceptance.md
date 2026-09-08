# Final Skill installation and E2E acceptance

## Current production status

**Skill trigger: PASS.** A fresh Codex context discovered the installed
`meridian-alpha` Skill and confirmed that **“运行今天的 Meridian”** maps to the
canonical Schwab-Paper command. The runtime did start successfully from that
command on the persistent default account.

**Paper execution: BLOCKED.** The live run happened while NYSE was `CLOSED`.
Yahoo observations were `STALE` and Stooq was `UNAVAILABLE` with HTTP 404, so
Meridian correctly created no fill and did not send a research HTTP request.
This is an external-data blocker, not a Skill-routing failure.

## Skill installation and reload

The user-provided legacy paths were absent:

- `E:\CSDIY\Vibe Coding Project\personal-alpha-terminal-skill\skill`
- `C:\Users\Administrator\.codex\skills\personal-alpha-terminal`

The actual Skill source and installation are:

- repository: `E:\CSDIY\Vibe Coding Project\meridian-alpha\skills\meridian-alpha`
- installed: `C:\Users\YOGA Pro16\.codex\skills\meridian-alpha`

Their `SKILL.md` files have the same SHA-256:
`FE37028C99EF43CBDFDA8BEDC0959D1D759B7CEB4266A9F1F84E0C35FB000AA2`.
There was no local divergence to overwrite, so no backup or sync write was
needed.

A fresh Codex task (`01a07fdb-a624-7622-95c0-456e36436c98`) independently
discovered `meridian-alpha` and read the installed instructions. It confirmed:

- trigger: `运行今天的 Meridian`
- canonical command: `scripts/run_meridian.ps1 paper run --account Schwab-Paper --json`
- default account: `Schwab-Paper`
- initialization: USD 100,000.00 once only; later runs load the persistent ledger.

## Bundled resource audit

The live source and installed Skill trees now match across 10 resources (tree
SHA-256: `ac547a1327bed18499992ad264e1b1595fa7c67214e01135b132ca7acfd451fd`).
The old helper scripts and fixture were retained as files but made safe:

- `scripts/preflight.py` and `scripts/run_daily.py` now return
  `SKILL_HELPER_RETIRED` with the current canonical command; they do not accept
  a legacy profile, fixture, snapshot, or create a parallel workflow.
- The fixture is `TEMPLATE_ONLY_NOT_RUNTIME_INPUT`.
- Supporting references now document only the canonical Schwab-Paper workflow
  and the separate explicit real-Host path.

`skill-creator` validation passed with UTF-8 enabled. Existing installed
`SKILL.*` historical backups were preserved and remain inactive.

## Default-account E2E

The canonical command was run twice against the default runtime. Both runs had
`runtime_status = PASS`, produced canonical and paper JSON/Markdown reports,
and returned `PAPER_BLOCKED` for the closed-market inputs. The report run IDs
were `daily-747f4a84da90968098b4eee5` and
`daily-02c224868194d290c146632a`.

The repeated trigger created no fills. Read-only `paper status`, `paper history`
and `paper trades` calls from separate processes showed the same durable state:
Schwab-Paper, USD 100,000.00 starting capital, USD 100,000.00 cash and NAV,
zero positions, zero trades, and ledger version 0. No normal command reset the
account.

Research routing was invoked through canonical daily but did not issue an HTTP
request because `RESEARCH_INPUT_NOT_READY` fail-closed on stale market inputs.
Decision and gates were evaluated; decision was `BLOCKED_STALE_MARKET`.
Public quotes remain uncertified, manual authority remains blocked, and broker
submission remains disabled.

## Windows, wheel, and regression evidence

The default Windows EFS/AppContainer report directory allowed staging writes but
rejected atomic rename with WinError 17. A narrow report-publication repair now
uses atomic rename normally and, only for that error with a new destination,
creates the final report exclusively, fsyncs it, and verifies its content. The
post-fix default-runtime run wrote all four reports.

- 385 tests passed; focused report/paper/failure tests: 34 passed.
- Ruff passed; Pyright reported 0 errors and 0 warnings; `pip check` passed.
- The current wheel built successfully and its read-only `paper status` smoke
  passed from `%TEMP%`, outside the checkout.
- The canonical PowerShell launcher also passed from `%TEMP%`.

The existing user report was preserved with SHA-256
`FEA9457D5694DAC11E5F428B1451039C0E6A7F0CC4627039BAA7D2B351342D64`.

## Final verdict

**PASS:** in a fresh Codex session, the user can type only **“运行今天的
Meridian”** to start the canonical Schwab-Paper daily workflow using the
persistent USD 100,000.00 account.

It is not an assertion that a paper trade occurred. Current paper execution is
**BLOCKED** until a NYSE regular session has fresh public observations and a
validated advisory-research result. Retrying the unchanged trigger in that
context is the next exact action.
