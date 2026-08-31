# Gate 6K — ChatGPT mobile portable Skill report

## Status

`MOBILE_INSTALLABLE_SKILL_PACKAGE_READY`

The Skill package is self-contained for instructions, references, capability
preflight, and a safe core-delegating wrapper. It does not require MCP,
localhost, developer mode, a Windows checkout, PowerShell, or shell activation.
It explicitly returns `MERIDIAN_RUNTIME_UNAVAILABLE` when the installed
Meridian core is not available; it never recreates investment calculations in
free-form text.

| Gate | Result |
|---|---|
| Agent Skill valid | `SKILL_PACKAGE_VALID` (10 files) |
| Clean-room extraction | PASS; ZIP extracted into an empty temporary directory |
| Absolute paths | NONE in package or clean-room output |
| Required dependencies | Python 3.12+ standard library, sanitized JSON input, Host capability or supplied envelope |
| Optional dependencies | Installed Meridian core, pinned pydantic/PyYAML/MCP, certified SEC/market/quote inputs, bounded DeepSeek |
| HOST_NATIVE mode | DOCUMENTED and capability-gated |
| Mobile install package | `MOBILE_INSTALLABLE_SKILL_PACKAGE_READY` |
| ZIP SHA256 | bfabee756002259d623a9e0a07a5788b9b027b2a432ff881e5c1ed3a6d6c84c9 |
| GitHub release | NOT UPDATED; Gate 6J publication remains blocked by invalid GitHub auth |
| Mobile runtime proven | NO — no actual ChatGPT web/mobile Skills test occurred |
| MCP required | NO |

## Offline proof

The clean-room tests ran both TEST and REPLAY preflight with the bundled
synthetic cash-only fixture. Both reported an unavailable runtime when site
packages and the repository checkout were excluded. `run_daily.py` returned
sanitized JSON plus the Chinese report with `MERIDIAN_RUNTIME_UNAVAILABLE` and
`analysis_executed: false`. No source was imported through a developer path.

## Safety and blockers

- Broker: NONE.
- Schwab: NOT CONNECTED.
- Real orders: ZERO.
- Real Host input: absent.
- Certified execution quote: absent.
- Shadow observation period: incomplete.
- Gate 6J GitHub release: blocked until the user re-authenticates `gh`; no
  remote, tag, or release was created.
- Known P0: 0.
- Known P1: external Host input, execution-quote certification, observation
  period, and GitHub authentication for publication.

`MOBILE_RUNTIME_PROVEN` is intentionally not claimed. Verify the installed
Skill in the target ChatGPT surface using
`docs/mobile-install-verification-checklist.md` before assigning that label.