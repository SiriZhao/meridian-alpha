# ADR 0036: Isolated, predeclared horizon portfolio evaluation

Status: accepted, 2026-10-08. Extends the reviewed-close laboratory without
changing production scoring, allocation, risk, order planning or permissions.

## Problem

Signal IC and direction hit rates do not measure a self-financing portfolio.
Ignoring exposure, unused cash and transaction costs can make weak signals look
profitable. A decision timestamp can also be later than its information cutoff;
aligning features only to the decision admits unavailable information.

## Decision

`portfolio_lab` evaluates a caller-attested, predeclared fixed universe and
train/validation/test chronology. It fits no parameters and selects no winning
strategy. All challengers share complete reviewed rows, historical features,
benchmark provenance, partition boundaries and a fixed commission/slippage grid.
Labels crossing a later partition's publication boundary and overlapping held
intervals are purged. Inputs must match the frozen information cutoff exactly.

The operational challenger reuses the existing deterministic allocator and risk
overlay, including its OPERATIONAL_UNCLASSIFIED sector semantics. Unit NAV is
synthetic and never persisted as an account. The multi-factor recipe and existing
certified research modifier remain isolated. Missing certified research has zero
contribution and an explicit INSUFFICIENT_EVIDENCE comparison status. The CLI
does not deserialize uncertified claims into certificates or invoke an LLM.

Hypothetical fractional positions enter and exit each observed horizon. Both
entry and terminal fees reduce wealth; cash must cover entry costs. Cash earns
an explicitly assumed zero, including unobserved gaps. The benchmark is matched
horizon exposure with the same reserve/cost assumptions, **not** continuous SPY
buy-and-hold. Missing gap prices prohibit that stronger claim. Cost on terminal
wealth (including cash distributions) is a declared conservative approximation,
not an observed execution or market-impact model.

Cash distributions are not described as dividend-reinvested total return, which
has a different definition. See [S&P index mathematics](https://www.spglobal.com/spdji/en/methodology/article/index-mathematics-methodology/).
Reviewed session coverage remains bounded to the calendar documented by
[NYSE](https://www.nyse.com/trade/hours-calendars).

Only held-out horizon metrics are reported after training, validation and enough
test blocks exist. Endpoint drawdown is distinguished from unobserved intra-horizon
drawdown. Irregular horizons and unproven independence prohibit annualized Sharpe,
confidence intervals or an alpha significance claim. Confidence is not a defined
probability, so no Brier/ECE is fabricated. The conclusion remains
NO_DEMONSTRATED_ALPHA. Markdown is a lossless projection of the computed JSON.

## Limits and safety

Manual review/registration are attestations, not authenticated proofs. Fixed
universe membership is not market-wide survivorship coverage. The engine models
fractional hypothetical exposure, not actual order eligibility, integer rounding,
fills, intraday slippage or gap buy-and-hold returns. Synthetic tests of these
contracts are not real financial samples. Quote certification stays BLOCKED,
broker submission DISABLED and automatic promotion DISABLED. No canonical runtime
is written. A real financial comparison still requires qualified evidence.
