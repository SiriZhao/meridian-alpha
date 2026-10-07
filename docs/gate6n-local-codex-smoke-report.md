# Gate 6N — Local Codex Skill discovery and development smoke report

## Discovery and release identity

| Field | Result |
|---|---|
| Codex Skill discovered | YES — listed as `meridian-alpha` in this restarted Codex session’s available-skills registry |
| Skill source | `<USER_HOME>\.codex\skills\meridian-alpha` |
| Skill name/description | `name: meridian-alpha`; read-only US-equity decision-support description verified |
| Skill version | `meridian-alpha-skill-v1` |
| Gate 6M release reference | Source commit `3166beeb6f214a289ec4372ce713da7b076bd34a`; no `v1.0.0-rc1` tag exists |
| Installed manifest | `c7cb9bb7962e85050c5a77a9202bbb4832f663d219a97bb2b85b4202acb342d5` |
| Source/installed manifest | MATCH |
| Skill ZIP SHA256 | `8e770f7e858a774d2cf0357f4bc0bf44711301e11b15e08d7b5d36aec652ac47` |

Discovery is proven by the restarted Codex Skill registry, not inferred solely
from the filesystem. Backup copies are outside the active `skills` directory.

## Safe local smoke

| Check | Result |
|---|---|
| Local core | AVAILABLE — Python 3.12.14 and project environment |
| TEST mode | PASS — bundled sanitized fixture, deterministic analysis, `ANALYSIS_ONLY` |
| REPLAY mode | PASS — bundled sanitized fixture, `REPLAY_ONLY` SEC/DeepSeek semantics, no live providers |
| Production frozen LLM path | PASS — focused production/replay/release tests; 43 passed |
| Chinese report | PASS — UTF-8 mobile sections rendered; output explicitly non-enterable |
| Real-input negative test | PASS — no manual-ready output; `REAL_HOST_INPUT` and `EXECUTION_QUOTE_CERTIFICATION` blockers |
| Manual authority | PASS — Gate 6F tests enforce certificate + certified quote; current manual entry NO |

The natural system-status workflow used capability preflight first. With no
account supplied it reports `ACCOUNT_INPUT: MISSING`; TEST/REPLAY use only the
bundled synthetic snapshot. No conversation history was treated as account
truth.

## GitHub and safety

| Field | Result |
|---|---|
| GitHub release | NOT VERIFIED — no origin, repository, tag, or pre-release; `gh` is unauthenticated |
| CI | Local workflow configuration present; remote CI not reachable |
| Real Host | NO |
| Execution quote | NOT CERTIFIED |
| Manual entry | NO |
| Shadow sessions | 0 completed / 5 minimum / 10 preferred |
| Broker | NONE |
| Schwab | NOT CONNECTED |
| Real orders | ZERO |
| Known P0 | 0 |
| Known P1 | GitHub authentication/publication, real Host input, ExecutionQuote certification, minimum shadow observation |

`GITHUB_SKILL_RELEASE_READY` is not claimed because the personal GitHub
repository and pre-release do not exist. `LOCAL_CODEX_SKILL_INSTALLED`,
`LOCAL_CODEX_SKILL_DISCOVERY_PROVEN`, `LOCAL_CODEX_TEST_MODE_PROVEN`, and
`LOCAL_CODEX_REPLAY_MODE_PROVEN` are earned locally. No production Meridian
logic was changed to solve the installation or discovery issue.
