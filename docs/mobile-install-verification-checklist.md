# Mobile Skill installation verification checklist

This checklist is for a human test in the target ChatGPT web/mobile Skills
surface. Codex can validate the package, but cannot claim `MOBILE_RUNTIME_PROVEN`.

- [ ] Skill name `meridian-alpha` is visible after installation.
- [ ] Installed version/hash matches the released ZIP and `.sha256` file.
- [ ] `SKILL.md` loads and its three reference documents are accessible.
- [ ] The Skill reports capability preflight without printing secrets.
- [ ] A safe `TEST` invocation returns a Chinese report or an explicit
      `MERIDIAN_RUNTIME_UNAVAILABLE` blocker.
- [ ] A real account request never infers holdings from conversation history.
- [ ] Missing runtime, Host input, certified evidence, or quote fails closed.
- [ ] No broker login, Schwab authentication, order submission, cancel/replace,
      or assumed-fill capability is offered.
- [ ] No account identifiers, credentials, raw connector responses, or private
      runtime files appear in output.
- [ ] Only after this checklist passes in the actual target surface may a human
      record `MOBILE_RUNTIME_PROVEN` for that surface.