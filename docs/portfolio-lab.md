# Predeclared portfolio research replay

`meridian.portfolio_lab` extends descriptive signal evaluation into explicitly
hypothetical, self-financing horizon portfolios. It cannot submit orders, change
production policy, write accounts or promote strategies.

Read-only CLI:

```powershell
.\.venv\Scripts\python.exe -m meridian.alpha_lab portfolio --input .\experiment.json
```

`PortfolioReplayInput` contains a `PortfolioExperiment`, `LabInput` observations
and `ReviewedPricePair` receipts. The experiment declares a fixed universe,
registration/universe availability, validation/test boundaries, evaluation time,
unchanged risk-policy snapshot and a fixed commission/slippage grid. It fits no
parameters. CLI research contribution is zero; Python callers can supply only
existing certified, cutoff-matched research objects. Deserializing a claim or
ordinary confidence into a certificate is unsupported.

Cash, matched-horizon benchmark, current operational quant, fixed multi-factor
and quant-plus-certified-research share complete eligible cohorts. Missing
history/action/benchmark evidence blocks a cohort; public/synthetic origins do
not become financial evidence. Training/validation publication boundaries purge
unavailable labels, and overlapping held intervals are removed. Feature cutoff
must equal the frozen prediction's information cutoff, even if decision is later.

The model starts and ends each horizon in cash, uses fractional hypothetical
exposure and charges entry plus terminal-wealth costs. Entry cash must cover fees.
Unobserved gaps and idle cash earn an assumed zero. The benchmark has the same
cash reserve and costs; it is not continuous buy-and-hold. Terminal costs also
apply to retained distributions as a declared conservative approximation.

Outputs include held-out cumulative return, matched-benchmark excess, endpoint
drawdown, horizon volatility, exposure, absolute-weight concentration, traded
notional, hypothetical entry/exit count and cost sensitivity. All are descriptive
under the declared model, not observed fills or demonstrated alpha. Missing
partitions or too few test blocks produce INSUFFICIENT_EVIDENCE and null metrics.
Without full certified research coverage the LLM comparison remains insufficient.
No annualized return, intrahorizon drawdown, confidence-as-probability or spurious
significance is generated. Twenty blocks do not prove independence or alpha.

Receipts and registration are local attestations; stronger review governance and
PIT universe membership remain prerequisites for broader financial claims. Tests
use mock review receipts with explicit fixture source labels. They verify engine
contracts, not real market performance. See [ADR 0036](adr/0036-predeclared-horizon-portfolio-evaluation.md).
