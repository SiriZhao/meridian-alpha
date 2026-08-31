# ChatGPT/mobile Skill installation

The GitHub repository is source and distribution; a GitHub URL does not
automatically install a Skill in ChatGPT.

1. Download `dist/meridian-alpha-skill-v1.zip` and verify it against the
   adjacent `.sha256` file.
2. Where the surface exposes it, use **ChatGPT → Plugins → Skills → Create →
   Upload** (or install a Skill shared with the user/workspace). Product labels
   and availability vary by plan, workspace policy, and surface.
3. Desktop, web, and mobile may require separate installation or availability
   checks. Confirm the installed Skill name/version and hash.
4. The Meridian V1 workflow does not depend on a custom MCP App on mobile. If
   a Host can provide an authorized sanitized snapshot, pass that envelope to
   the Skill; otherwise provide the sanitized JSON manually.
5. A Skill installation proves package availability only. `MOBILE_RUNTIME_PROVEN`
   requires an actual successful run in the target ChatGPT Skills surface and
   must not be claimed from a ZIP or Codex clean-room test.

The Skill never scrapes browser accounts, requests credentials, logs in to a
broker, assumes fills, or creates an executable order. A manual draft is shown
only when the sealed seven-gate readiness certificate and certified execution
quote are both present.