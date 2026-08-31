# Security policy

Meridian Alpha is decision-support software with a manual-entry boundary. The
current V1 has no broker login, broker read/write surface, Schwab integration,
or automatic execution.

- Never commit API keys, DeepSeek keys, Alpaca/Polygon keys, OAuth secrets,
  tokens, account numbers, raw Host snapshots, connector payloads, or private
  logs.
- Keep credentials in an approved local secret manager or environment outside
  Git. Use `.env.example` only for redacted variable names and placeholders.
- If a credential is exposed, stop publishing, revoke/rotate it immediately,
  and report the exposure with the affected commit or artifact identified—but
  do not include the secret value.
- Manual drafts are human-review artifacts and are always `NOT_EXECUTED`.
  Recommendations never imply a fill; only a later sanitized Host snapshot can
  establish changed account state.

Report suspected security issues privately to the repository owner rather than
opening a public issue containing sensitive data.