# Alpha Fusion Contract

Only `CertifiedAgentSignal` can influence executable Alpha Fusion. Raw `AgentSignal`, graph rating, synthetic fixture, replay-unsafe packet, and failed research are non-executable.

```text
qualitative = mean(present fundamental/sentiment/news/valuation scores)
              or direction sign
quant_component = 0.45 * clamp(technical_score, -1, 1)
evidence_quality = min(1, evidence_count / 3)
bounded_regime = clamp(regime_multiplier, 0, 1)
research_component = 0.55 * qualitative * conviction * evidence_quality * bounded_regime
risk_penalty = supplied deterministic risk score, or 0 when optional risk is absent
final_alpha = clamp(quant_component + research_component - risk_penalty, -1, 1)
```

The research coefficient is bounded by policy. Quantities, weights, leverage, prices, and execution remain deterministic policy outputs.
