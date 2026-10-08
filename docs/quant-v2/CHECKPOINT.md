# Quant V2 recoverable checkpoint

Status: baseline audit and isolated validation in progress.

Checkout: `.worktrees/quant-engine-v2`, branch `codex/quant-engine-v2`.
Base: `414d869`, includes published canonical hardening after origin/main.
Original checkout and its pending work are preserved. Use the isolated
checkout's `.venv/Scripts/python.exe`; never change the canonical runtime.

Baseline log: `.tmp/quant-v2/baseline.log`.
Next: PIT feature contracts, scoring/regime, constrained portfolios, delayed
walk-forward replay, shadow integration, full verification and branch delivery.

User authorized development branch commit/push and optional PR, no merge.
GPT-6.1 Sol High requested; this session exposes no model-switch control, so
the active model selection cannot be independently verified or changed.
