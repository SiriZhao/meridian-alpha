# Gate 6M — GitHub release and local Codex installation report

## Publication status

| Field | Result |
|---|---|
| GitHub owner | UNAVAILABLE — `gh auth` has no authenticated account |
| Repository | NOT CREATED / NOT VERIFIED |
| Visibility | NOT APPLICABLE |
| Branch | `main` |
| Release commit | `3166beeb6f214a289ec4372ce713da7b076bd34a` |
| Tag | NONE — no immutable tag was created |
| Release URL | NOT AVAILABLE |
| CI status | Local CI configuration present; remote CI not triggered |
| Release asset verified | NO — GitHub publication is blocked |

GitHub connectivity was repaired locally: loopback GitHub hosts mappings were
removed from the Windows hosts file with a timestamped backup, DNS cache was
flushed, `github.com` resolved publicly, and TCP 443 succeeded. The subsequent
browser/device authorization reached GitHub but the CLI token exchange failed;
no credential was printed or retained by this run. No remote, push, tag,
release, issue, or label was created.

## Skill and Codex installation

| Field | Result |
|---|---|
| Skill ZIP | `dist/meridian-alpha-skill-v1.zip` |
| Actual ZIP SHA256 | `8e770f7e858a774d2cf0357f4bc0bf44711301e11b15e08d7b5d36aec652ac47` |
| Package validation | `SKILL_PACKAGE_VALID` (source, installed, and clean-room ZIP) |
| Codex home | `C:\Users\YOGA Pro16\.codex` |
| Installed Skill path | `C:\Users\YOGA Pro16\.codex\skills\meridian-alpha` |
| Install method | `LOCAL_VERIFIED_FALLBACK` from release commit; GitHub release unavailable |
| Installed manifest | `c7cb9bb7962e85050c5a77a9202bbb4832f663d219a97bb2b85b4202acb342d5` |
| Source/installed manifest match | YES |
| TEST smoke | PASS — local Meridian core, `ANALYSIS_ONLY`, UTF-8 Chinese report |
| REPLAY smoke | PASS — bundled sanitized fixture, `ANALYSIS_ONLY` |
| Mobile runtime proven | NO — no ChatGPT web/mobile Skills-surface test |

The portable Skill contains no developer absolute paths, secrets, runtime
ledgers, broker modules, or bytecode. Local development uses the process-local
`MERIDIAN_PROJECT_ROOT` locator; it is not embedded in the Skill package.

## Safety and remaining blockers

- Real Host input: NO.
- ExecutionQuote: NOT CERTIFIED.
- Manual entry: NO.
- Shadow sessions: 0 completed / 5 minimum / 10 preferred.
- Broker: NONE.
- Schwab: NOT CONNECTED.
- Real orders: ZERO.
- Known P0: 0.
- Known P1: GitHub authentication/publication, real Host smoke, ExecutionQuote
  certification, and minimum shadow observation period.

The release milestone `GITHUB_SKILL_RELEASE_READY` is not claimed because no
authenticated personal repository or pre-release exists. `LOCAL_CODEX_SKILL_INSTALLED`
is complete. Restart Codex before relying on automatic Skill discovery.
