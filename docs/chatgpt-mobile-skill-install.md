# ChatGPT/mobile Skill installation

The GitHub repository is source and distribution; a GitHub URL does not
automatically install a Skill in ChatGPT.

1. Download `dist/meridian-alpha-skill-v1.zip` and verify it against the
   adjacent `.sha256` file.
2. In a ChatGPT surface that supports Skills, use the Skills UI or upload flow
   to install the ZIP. Availability depends on the account plan, workspace
   policy, and product surface.
3. Desktop, web, and mobile may require separate installation or availability
   checks. Confirm the installed Skill name/version and hash.
4. The Meridian V1 workflow does not depend on a custom MCP App on mobile. If
   a Host can provide an authorized sanitized snapshot, pass that envelope to
   the Skill; otherwise provide the sanitized JSON manually.

The Skill never scrapes browser accounts, requests credentials, logs in to a
broker, assumes fills, or creates an executable order. A manual draft is shown
only when the sealed seven-gate readiness certificate and certified execution
quote are both present.