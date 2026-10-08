# Quant V2 recoverable checkpoint

Status: implementation and targeted tests complete; merged full validation,
final diagnostic freeze, fresh-clone verification and remote delivery pending.

Checkout: `.worktrees/quant-engine-v2`, branch `codex/quant-engine-v2`.
Base: `414d869`, plus published Phase 4 forward-evidence foundation `09e95dd`.
Original checkout and its pending work are preserved. Use the isolated
checkout's `.venv/Scripts/python.exe`; never change the canonical runtime.

Baseline log: `.tmp/quant-v2/baseline.log`.
Implemented: PIT feature contracts, scoring/regime, constrained portfolios,
delayed walk-forward replay, immutable shadow and separate paper-review packet.
88 new quant tests cover anti-lookahead, missing data, costs, risk and isolation.
The original checkout's additional uncommitted Phase 4 work remains excluded.
Next: full verification, final synthetic experiment registry and branch delivery.
Financial alpha status: INSUFFICIENT_EVIDENCE. Public history audit rejected raw,
uncertified, currently retrieved bars for financial PIT evidence. Synthetic
experiments demonstrate reproducibility only. No canonical runtime writes.

User authorized development branch commit/push and optional PR, no merge.
GPT-6.1 Sol High requested; this session exposes no model-switch control, so
the active model selection cannot be independently verified or changed.
