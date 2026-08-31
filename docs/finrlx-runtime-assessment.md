# FinRL-X runtime assessment

The reviewed upstream is the AI4Finance FinRL-Trading/FinRL-X repository at
the pinned review commit `e65d6f0483ead7d2ef4a5fc940cdf960392a25c1`, version
`2.0.2`, declaring Apache-2.0. It requires a separate Python 3.11/3.12
environment and includes optional ML, backtest, and Alpaca-capable execution
components.

Gate 6D performs a non-importing local runtime inspection. No compatible
FinRL-X package, reviewed allocator-only adapter, or validated artifact is
installed in Meridian's `.venv`; therefore the runtime remains
`MODEL_UNAVAILABLE`. Meridian does not add the heavy dependency to the main
environment, import execution components, train a model, or fabricate OOS and
walk-forward metrics. A future isolated install must pin the commit above,
record the dependency/license review, expose allocator inference only, and pass
the mechanical artifact/OOS gate before shadow inference can run.
