# FIXTURE ONLY — 合成回归示例，非今日行情

# MERIDIAN ALPHA — LIVE SESSION REPORT

Run ID: FIXTURE_ONLY_NOT_LIVE
Generated At: 2021-02-11T21:00:00+00:00
Market Session: FIXTURE_NOT_CURRENT_SESSION
Market Data As Of: None
Provider: UNAVAILABLE
Freshness: UNAVAILABLE

## Portfolio summary

{}

## Market regime and current signals

{}

## Completed-session historical features

{}

## LLM research

{}

## Risk review

{}

## Action table

| Symbol | Observed price | GPT opinion | Uncalibrated narrative confidence | Research zone anchor | Invalidation | V1 reference guidance | Main reason |
|---|---:|---|---:|---:|---:|---|---|

## Top action now

No validated LLM advice available.
Avoid now: UNAVAILABLE
Doing nothing: UNAVAILABLE

## Acceptance

{
  "quant": "FIXTURE_COMPUTED",
  "llm": "NOT_RUN",
  "report": "PASS"
}
Blockers: FIXTURE_ONLY_NOT_LIVE_ACCEPTANCE, INSUFFICIENT_VERIFIED_HISTORY

Acceptance pending:
AUTO_EXECUTION = DISABLED; MANUAL_CONFIRMATION_REQUIRED = TRUE; ORDER_AUTHORITY = NONE
Research price zones are deterministic observations, not executable limit-order tickets.

## Quant 与 GPT 决策来源

QUANT_V1_BASELINE：原 canonical 默认；本报告的旧目标只是 live 参考比较。
V2.2_SHADOW：确定性研究挑战者；GPT_ADVISORY：模型解释，无修改分数或交易授权。
共享分析截止时点：2021-02-11T21:00:00Z
证据指纹：79c96150593c3f746194d43911d8d7f474f73ea8bf28cfb0f7a54159356b45c5

## 中文研究观察

### UNKNOWN（名称未获核验） / AAPL

AAPL：定量通道为 INSUFFICIENT_VERIFIED_HISTORY；当前报价状态 LIVE；研究分类 WAIT_FOR_EVIDENCE。缺失因子与价格条件保持 UNKNOWN，分数不代表获利概率。

当前观察价：78.23489681886724429774523624；带日期参考价：78.23489681886724429774523624；时间：2021-02-11T16:00:00-05:00；来源：FIXTURE_ONLY；声明延迟：None。

```json
{
  "symbol": "AAPL",
  "company": "UNKNOWN（名称未获核验）",
  "observed_price": "78.23489681886724429774523624",
  "dated_reference_price": "78.23489681886724429774523624",
  "observation_at": "2021-02-11T16:00:00-05:00",
  "timezone": "America/New_York",
  "provider": "FIXTURE_ONLY",
  "feed_delay_seconds": null,
  "history_quality": "INSUFFICIENT_VERIFIED_HISTORY",
  "momentum_3m": "0.018397591173764765084444459",
  "momentum_6m": "0.026024165688286693107362936",
  "relative_strength_6m": "-0.073438422068598996912654499",
  "trend_sma60": "78.2021297954666561490133691",
  "volatility_60": "0.06770664281582535286734174824",
  "drawdown_252": "-0.0228223143783107260305463560",
  "quant_score": null,
  "quant_rank": null,
  "factor_attribution": [
    {
      "version": "quant-factor-contribution.v2.2",
      "name": "momentum_3m",
      "group": "absolute",
      "symbol": "AAPL",
      "as_of": "2021-02-11T21:00:00Z",
      "availability_cutoff": "2021-02-11T21:00:00Z",
      "provenance": [
        "fa75f0310d6b0fca56ce688a2584f741a963d7d9850b20f485de68b023a1e363",
        "synthetic-diagnostic:ENGINEERING_FIXTURE_NOT_REAL_MARKET_DATA"
      ],
      "lookback": 63,
      "raw": "0.018397591173764765084444459",
      "normalized": "0.5624920526444937746366283638",
      "weight": "0.100",
      "contribution": "0.05624920526444937746366283638",
      "missing_reason": null,
      "transformation": "FIXED_SCALE_AND_BOUNDED_TIED_RANK_BLEND"
    },
    {
      "version": "quant-factor-contribution.v2.2",
      "name": "momentum_6m",
      "group": "absolute",
      "symbol": "AAPL",
      "as_of": "2021-02-11T21:00:00Z",
      "availability_cutoff": "2021-02-11T21:00:00Z",
      "provenance": [
        "fa75f0310d6b0fca56ce688a2584f741a963d7d9850b20f485de68b023a1e363",
        "synthetic-diagnostic:ENGINEERING_FIXTURE_NOT_REAL_MARKET_DATA"
      ],
      "lookback": 126,
      "raw": "0.026024165688286693107362936",
      "normalized": "0.5673818939762185398197907357",
      "weight": "0.150",
      "contribution": "0.08510728409643278097296861036",
      "missing_reason": null,
      "transformation": "FIXED_SCALE_AND_BOUNDED_TIED_RANK_BLEND"
    },
    {
      "version": "quant-factor-contribution.v2.2",
      "name": "momentum_12_1",
      "group": "absolute",
      "symbol": "AAPL",
      "as_of": "2021-02-11T21:00:00Z",
      "availability_cutoff": "2021-02-11T21:00:00Z",
      "provenance": [
        "fa75f0310d6b0fca56ce688a2584f741a963d7d9850b20f485de68b023a1e363",
        "synthetic-diagnostic:ENGINEERING_FIXTURE_NOT_REAL_MARKET_DATA"
      ],
      "lookback": 252,
      "raw": "0.115174541914575159333662418",
      "normalized": "0.7194332155840658525195352485",
      "weight": "0.250",
      "contribution": "0.1798583038960164631298838121",
      "missing_reason": null,
      "transformation": "FIXED_SCALE_AND_BOUNDED_TIED_RANK_BLEND"
    },
    {
      "version": "quant-factor-contribution.v2.2",
      "name": "relative_momentum_6m",
      "group": "relative",
      "symbol": "AAPL",
      "as_of": "2021-02-11T21:00:00Z",
      "availability_cutoff": "2021-02-11T21:00:00Z",
      "provenance": [
        "fa75f0310d6b0fca56ce688a2584f741a963d7d9850b20f485de68b023a1e363",
        "synthetic-diagnostic:ENGINEERING_FIXTURE_NOT_REAL_MARKET_DATA"
      ],
      "lookback": 126,
      "raw": "-0.073438422068598996912654499",
      "normalized": "0.2760402489591206694093482806",
      "weight": "0.25",
      "contribution": "0.06901006223978016735233707015",
      "missing_reason": null,
      "transformation": "FIXED_SCALE_AND_BOUNDED_TIED_RANK_BLEND"
    },
    {
      "version": "quant-factor-contribution.v2.2",
      "name": "medium_distance",
      "group": "trend",
      "symbol": "AAPL",
      "as_of": "2021-02-11T21:00:00Z",
      "availability_cutoff": "2021-02-11T21:00:00Z",
      "provenance": [
        "fa75f0310d6b0fca56ce688a2584f741a963d7d9850b20f485de68b023a1e363",
        "synthetic-diagnostic:ENGINEERING_FIXTURE_NOT_REAL_MARKET_DATA"
      ],
      "lookback": 60,
      "raw": "0.000419004232829572360244113",
      "normalized": "0.4757185796309815682753058517",
      "weight": "0.125",
      "contribution": "0.05946482245387269603441323146",
      "missing_reason": null,
      "transformation": "FIXED_SCALE_AND_BOUNDED_TIED_RANK_BLEND"
    },
    {
      "version": "quant-factor-contribution.v2.2",
      "name": "trend_persistence",
      "group": "trend",
      "symbol": "AAPL",
      "as_of": "2021-02-11T21:00:00Z",
      "availability_cutoff": "2021-02-11T21:00:00Z",
      "provenance": [
        "fa75f0310d6b0fca56ce688a2584f741a963d7d9850b20f485de68b023a1e363",
        "synthetic-diagnostic:ENGINEERING_FIXTURE_NOT_REAL_MARKET_DATA"
      ],
      "lookback": 60,
      "raw": "-0.0166666666666666666666666667",
      "normalized": "0.4456730769230769230769230768",
      "weight": "0.125",
      "contribution": "0.05570913461538461538461538460",
      "missing_reason": null,
      "transformation": "FIXED_SCALE_AND_BOUNDED_TIED_RANK_BLEND"
    }
  ],
  "signal_persistence": null,
  "regime": {
    "version": "quant-regime-v2.1",
    "as_of": "2021-02-11T21:00:00Z",
    "trend": "TRENDING_UP",
    "volatility": "HIGH_VOLATILITY",
    "drawdown_stress": false,
    "risk_multiplier": "0.5",
    "exposure_ceiling": "0.5",
    "rebalance_urgency": "RISK_REDUCTION",
    "input_hash": "7eae7da4789cd81f6d20515a37ff91f7614cac5057520193f8d9d6abf58a5a4b",
    "reasons": [
      "SPY_TREND_AND_TRAILING_VOLATILITY"
    ]
  },
  "regime_is_prediction": false,
  "preferred_exposure": "0.195557",
  "feasible_exposure": "0.083333",
  "current_exposure": null,
  "cost_adjusted_exposure": null,
  "concentration_effect": [
    "POSITION_COUNT_CAP_AND_SINGLE_INVERSE_VOLATILITY_SIZING",
    "SECTOR_EXPOSURE_CAP:SYNTHETIC_SECTOR",
    "FRESH_ACCOUNT_REQUIRED_NO_CURRENCY_COST_ESTIMATE"
  ],
  "decision_category": "WAIT_FOR_EVIDENCE",
  "price_condition": {
    "observed_price": "78.23489681886724429774523624",
    "quote_hash": "3e4204735c6608b7edaf0c6b42c7b60a411001ea400a4f0d48509b16f4a89402",
    "observation_at": "2021-02-11T21:00:00+00:00",
    "timezone": "America/New_York",
    "quantitative_entry_zone": null,
    "method": null,
    "assumptions": [],
    "fair_value": null,
    "user_approved_executable_limit": null,
    "assessment": "WAIT_FOR_EVIDENCE",
    "invalidation_condition": "Recompute after a new completed session, corporate action or stale observation.",
    "reason": "Qualified ATR/price basis/current observation unavailable; no invented entry price."
  },
  "catalysts": "UNKNOWN：未提供带来源与时间的新闻或财务证据。",
  "gpt_interpretation": "UNKNOWN：模型未完成，保留定量证据。",
  "scenarios": "UNKNOWN：没有已验证的模型情景输出。",
  "opposing_evidence": [
    "FRESH_ACCOUNT_REQUIRED_NO_CURRENCY_COST_ESTIMATE",
    "PUBLIC_RETRIEVAL_AFTER_CUTOFF",
    "INSUFFICIENT_VERIFIED_HISTORY"
  ],
  "monitoring_trigger": "等待新鲜报价、可信复权历史与企业行动证据；按同一截止时点重新计算。",
  "invalidation_condition": "Recompute after a new completed session, corporate action or stale observation.",
  "no_action_reasons": [
    "FRESH_ACCOUNT_REQUIRED_NO_CURRENCY_COST_ESTIMATE",
    "INSUFFICIENT_VERIFIED_HISTORY",
    "PUBLIC_RETRIEVAL_AFTER_CUTOFF"
  ],
  "important_unknowns": [
    "内在价值",
    "新闻催化剂",
    "校准预期收益",
    "ETF 穿透重叠",
    "当前账户风险上下文"
  ],
  "manual_requirements": [
    "这是研究分类，不是券商订单。",
    "独立核对账户、报价和风险；真实订单逐笔人工批准。"
  ],
  "quant_engine": "V2.2_SHADOW",
  "gpt_engine": "GPT_ADVISORY",
  "predictive_confidence": null,
  "trade_authorized": false,
  "explanation": "AAPL：定量通道为 INSUFFICIENT_VERIFIED_HISTORY；当前报价状态 LIVE；研究分类 WAIT_FOR_EVIDENCE。缺失因子与价格条件保持 UNKNOWN，分数不代表获利概率。"
}
```

### UNKNOWN（名称未获核验） / MSFT

MSFT：定量通道为 INSUFFICIENT_VERIFIED_HISTORY；当前报价状态 LIVE；研究分类 WAIT_FOR_EVIDENCE。缺失因子与价格条件保持 UNKNOWN，分数不代表获利概率。

当前观察价：102.1436122202917284464820861；带日期参考价：102.1436122202917284464820861；时间：2021-02-11T16:00:00-05:00；来源：FIXTURE_ONLY；声明延迟：None。

```json
{
  "symbol": "MSFT",
  "company": "UNKNOWN（名称未获核验）",
  "observed_price": "102.1436122202917284464820861",
  "dated_reference_price": "102.1436122202917284464820861",
  "observation_at": "2021-02-11T16:00:00-05:00",
  "timezone": "America/New_York",
  "provider": "FIXTURE_ONLY",
  "feed_delay_seconds": null,
  "history_quality": "INSUFFICIENT_VERIFIED_HISTORY",
  "momentum_3m": "0.009502521702052085765972601",
  "momentum_6m": "0.038918007167158275474943906",
  "relative_strength_6m": "-0.060544580589727414545073529",
  "trend_sma60": "101.9039872792888393996214529",
  "volatility_60": "0.06769443553259702521412871245",
  "drawdown_252": "-0.0224089216580147217680102347",
  "quant_score": null,
  "quant_rank": null,
  "factor_attribution": [
    {
      "version": "quant-factor-contribution.v2.2",
      "name": "momentum_3m",
      "group": "absolute",
      "symbol": "MSFT",
      "as_of": "2021-02-11T21:00:00Z",
      "availability_cutoff": "2021-02-11T21:00:00Z",
      "provenance": [
        "c2291838772cd3a8bbac83e67f48c201471df801c286c4e247754e1b16f29236",
        "synthetic-diagnostic:ENGINEERING_FIXTURE_NOT_REAL_MARKET_DATA"
      ],
      "lookback": 63,
      "raw": "0.009502521702052085765972601",
      "normalized": "0.5120102975154062465213336478",
      "weight": "0.100",
      "contribution": "0.05120102975154062465213336478",
      "missing_reason": null,
      "transformation": "FIXED_SCALE_AND_BOUNDED_TIED_RANK_BLEND"
    },
    {
      "version": "quant-factor-contribution.v2.2",
      "name": "momentum_6m",
      "group": "absolute",
      "symbol": "MSFT",
      "as_of": "2021-02-11T21:00:00Z",
      "availability_cutoff": "2021-02-11T21:00:00Z",
      "provenance": [
        "c2291838772cd3a8bbac83e67f48c201471df801c286c4e247754e1b16f29236",
        "synthetic-diagnostic:ENGINEERING_FIXTURE_NOT_REAL_MARKET_DATA"
      ],
      "lookback": 126,
      "raw": "0.038918007167158275474943906",
      "normalized": "0.6201947993504329369921689104",
      "weight": "0.150",
      "contribution": "0.09302921990256494054882533656",
      "missing_reason": null,
      "transformation": "FIXED_SCALE_AND_BOUNDED_TIED_RANK_BLEND"
    },
    {
      "version": "quant-factor-contribution.v2.2",
      "name": "momentum_12_1",
      "group": "absolute",
      "symbol": "MSFT",
      "as_of": "2021-02-11T21:00:00Z",
      "availability_cutoff": "2021-02-11T21:00:00Z",
      "provenance": [
        "c2291838772cd3a8bbac83e67f48c201471df801c286c4e247754e1b16f29236",
        "synthetic-diagnostic:ENGINEERING_FIXTURE_NOT_REAL_MARKET_DATA"
      ],
      "lookback": 252,
      "raw": "0.129808590197781645914637700",
      "normalized": "0.7706205562031185829119013966",
      "weight": "0.250",
      "contribution": "0.1926551390507796457279753492",
      "missing_reason": null,
      "transformation": "FIXED_SCALE_AND_BOUNDED_TIED_RANK_BLEND"
    },
    {
      "version": "quant-factor-contribution.v2.2",
      "name": "relative_momentum_6m",
      "group": "relative",
      "symbol": "MSFT",
      "as_of": "2021-02-11T21:00:00Z",
      "availability_cutoff": "2021-02-11T21:00:00Z",
      "provenance": [
        "c2291838772cd3a8bbac83e67f48c201471df801c286c4e247754e1b16f29236",
        "synthetic-diagnostic:ENGINEERING_FIXTURE_NOT_REAL_MARKET_DATA"
      ],
      "lookback": 126,
      "raw": "-0.060544580589727414545073529",
      "normalized": "0.3162069759228879677031710204",
      "weight": "0.25",
      "contribution": "0.07905174398072199192579275510",
      "missing_reason": null,
      "transformation": "FIXED_SCALE_AND_BOUNDED_TIED_RANK_BLEND"
    },
    {
      "version": "quant-factor-contribution.v2.2",
      "name": "medium_distance",
      "group": "trend",
      "symbol": "MSFT",
      "as_of": "2021-02-11T21:00:00Z",
      "availability_cutoff": "2021-02-11T21:00:00Z",
      "provenance": [
        "c2291838772cd3a8bbac83e67f48c201471df801c286c4e247754e1b16f29236",
        "synthetic-diagnostic:ENGINEERING_FIXTURE_NOT_REAL_MARKET_DATA"
      ],
      "lookback": 60,
      "raw": "0.002351477576104530667246256",
      "normalized": "0.5113991677848029627117274217",
      "weight": "0.125",
      "contribution": "0.06392489597310037033896592771",
      "missing_reason": null,
      "transformation": "FIXED_SCALE_AND_BOUNDED_TIED_RANK_BLEND"
    },
    {
      "version": "quant-factor-contribution.v2.2",
      "name": "trend_persistence",
      "group": "trend",
      "symbol": "MSFT",
      "as_of": "2021-02-11T21:00:00Z",
      "availability_cutoff": "2021-02-11T21:00:00Z",
      "provenance": [
        "c2291838772cd3a8bbac83e67f48c201471df801c286c4e247754e1b16f29236",
        "synthetic-diagnostic:ENGINEERING_FIXTURE_NOT_REAL_MARKET_DATA"
      ],
      "lookback": 60,
      "raw": "-0.0166666666666666666666666667",
      "normalized": "0.4456730769230769230769230768",
      "weight": "0.125",
      "contribution": "0.05570913461538461538461538460",
      "missing_reason": null,
      "transformation": "FIXED_SCALE_AND_BOUNDED_TIED_RANK_BLEND"
    }
  ],
  "signal_persistence": null,
  "regime": {
    "version": "quant-regime-v2.1",
    "as_of": "2021-02-11T21:00:00Z",
    "trend": "TRENDING_UP",
    "volatility": "HIGH_VOLATILITY",
    "drawdown_stress": false,
    "risk_multiplier": "0.5",
    "exposure_ceiling": "0.5",
    "rebalance_urgency": "RISK_REDUCTION",
    "input_hash": "7eae7da4789cd81f6d20515a37ff91f7614cac5057520193f8d9d6abf58a5a4b",
    "reasons": [
      "SPY_TREND_AND_TRAILING_VOLATILITY"
    ]
  },
  "regime_is_prediction": false,
  "preferred_exposure": "0.207232",
  "feasible_exposure": "0.083333",
  "current_exposure": null,
  "cost_adjusted_exposure": null,
  "concentration_effect": [
    "POSITION_COUNT_CAP_AND_SINGLE_INVERSE_VOLATILITY_SIZING",
    "SECTOR_EXPOSURE_CAP:SYNTHETIC_SECTOR",
    "FRESH_ACCOUNT_REQUIRED_NO_CURRENCY_COST_ESTIMATE"
  ],
  "decision_category": "WAIT_FOR_EVIDENCE",
  "price_condition": {
    "observed_price": "102.1436122202917284464820861",
    "quote_hash": "9afb09081f1dd0a96c41eaad8860a99afcc24402e50079c349f850299a4b4f9c",
    "observation_at": "2021-02-11T21:00:00+00:00",
    "timezone": "America/New_York",
    "quantitative_entry_zone": null,
    "method": null,
    "assumptions": [],
    "fair_value": null,
    "user_approved_executable_limit": null,
    "assessment": "WAIT_FOR_EVIDENCE",
    "invalidation_condition": "Recompute after a new completed session, corporate action or stale observation.",
    "reason": "Qualified ATR/price basis/current observation unavailable; no invented entry price."
  },
  "catalysts": "UNKNOWN：未提供带来源与时间的新闻或财务证据。",
  "gpt_interpretation": "UNKNOWN：模型未完成，保留定量证据。",
  "scenarios": "UNKNOWN：没有已验证的模型情景输出。",
  "opposing_evidence": [
    "FRESH_ACCOUNT_REQUIRED_NO_CURRENCY_COST_ESTIMATE",
    "PUBLIC_RETRIEVAL_AFTER_CUTOFF",
    "INSUFFICIENT_VERIFIED_HISTORY"
  ],
  "monitoring_trigger": "等待新鲜报价、可信复权历史与企业行动证据；按同一截止时点重新计算。",
  "invalidation_condition": "Recompute after a new completed session, corporate action or stale observation.",
  "no_action_reasons": [
    "FRESH_ACCOUNT_REQUIRED_NO_CURRENCY_COST_ESTIMATE",
    "INSUFFICIENT_VERIFIED_HISTORY",
    "PUBLIC_RETRIEVAL_AFTER_CUTOFF"
  ],
  "important_unknowns": [
    "内在价值",
    "新闻催化剂",
    "校准预期收益",
    "ETF 穿透重叠",
    "当前账户风险上下文"
  ],
  "manual_requirements": [
    "这是研究分类，不是券商订单。",
    "独立核对账户、报价和风险；真实订单逐笔人工批准。"
  ],
  "quant_engine": "V2.2_SHADOW",
  "gpt_engine": "GPT_ADVISORY",
  "predictive_confidence": null,
  "trade_authorized": false,
  "explanation": "MSFT：定量通道为 INSUFFICIENT_VERIFIED_HISTORY；当前报价状态 LIVE；研究分类 WAIT_FOR_EVIDENCE。缺失因子与价格条件保持 UNKNOWN，分数不代表获利概率。"
}
```

### UNKNOWN（名称未获核验） / NVDA

NVDA：定量通道为 INSUFFICIENT_VERIFIED_HISTORY；当前报价状态 LIVE；研究分类 WAIT_FOR_EVIDENCE。缺失因子与价格条件保持 UNKNOWN，分数不代表获利概率。

当前观察价：127.0632811719226998695736667；带日期参考价：127.0632811719226998695736667；时间：2021-02-11T16:00:00-05:00；来源：FIXTURE_ONLY；声明延迟：None。

```json
{
  "symbol": "NVDA",
  "company": "UNKNOWN（名称未获核验）",
  "observed_price": "127.0632811719226998695736667",
  "dated_reference_price": "127.0632811719226998695736667",
  "observation_at": "2021-02-11T16:00:00-05:00",
  "timezone": "America/New_York",
  "provider": "FIXTURE_ONLY",
  "feed_delay_seconds": null,
  "history_quality": "INSUFFICIENT_VERIFIED_HISTORY",
  "momentum_3m": "0.018828617595818829033457359",
  "momentum_6m": "0.071393615242919871420420339",
  "relative_strength_6m": "-0.028068972513965818599597096",
  "trend_sma60": "125.2296478228147117046496550",
  "volatility_60": "0.06782316723512024328913608954",
  "drawdown_252": "-0.0219978545336030347378296466",
  "quant_score": null,
  "quant_rank": null,
  "factor_attribution": [
    {
      "version": "quant-factor-contribution.v2.2",
      "name": "momentum_3m",
      "group": "absolute",
      "symbol": "NVDA",
      "as_of": "2021-02-11T21:00:00Z",
      "availability_cutoff": "2021-02-11T21:00:00Z",
      "provenance": [
        "553984518adceebc897ac194bebbd62611a21811ac7fe16d39f46946ec7c2236",
        "synthetic-diagnostic:ENGINEERING_FIXTURE_NOT_REAL_MARKET_DATA"
      ],
      "lookback": 63,
      "raw": "0.018828617595818829033457359",
      "normalized": "0.5826589934878836908547682017",
      "weight": "0.100",
      "contribution": "0.05826589934878836908547682017",
      "missing_reason": null,
      "transformation": "FIXED_SCALE_AND_BOUNDED_TIED_RANK_BLEND"
    },
    {
      "version": "quant-factor-contribution.v2.2",
      "name": "momentum_6m",
      "group": "absolute",
      "symbol": "NVDA",
      "as_of": "2021-02-11T21:00:00Z",
      "availability_cutoff": "2021-02-11T21:00:00Z",
      "provenance": [
        "553984518adceebc897ac194bebbd62611a21811ac7fe16d39f46946ec7c2236",
        "synthetic-diagnostic:ENGINEERING_FIXTURE_NOT_REAL_MARKET_DATA"
      ],
      "lookback": 126,
      "raw": "0.071393615242919871420420339",
      "normalized": "0.7020283086022552449084290748",
      "weight": "0.150",
      "contribution": "0.1053042462903382867362643612",
      "missing_reason": null,
      "transformation": "FIXED_SCALE_AND_BOUNDED_TIED_RANK_BLEND"
    },
    {
      "version": "quant-factor-contribution.v2.2",
      "name": "momentum_12_1",
      "group": "absolute",
      "symbol": "NVDA",
      "as_of": "2021-02-11T21:00:00Z",
      "availability_cutoff": "2021-02-11T21:00:00Z",
      "provenance": [
        "553984518adceebc897ac194bebbd62611a21811ac7fe16d39f46946ec7c2236",
        "synthetic-diagnostic:ENGINEERING_FIXTURE_NOT_REAL_MARKET_DATA"
      ],
      "lookback": 252,
      "raw": "0.128365100168091669959885542",
      "normalized": "0.7505984319475393964978996659",
      "weight": "0.250",
      "contribution": "0.1876496079868848491244749165",
      "missing_reason": null,
      "transformation": "FIXED_SCALE_AND_BOUNDED_TIED_RANK_BLEND"
    },
    {
      "version": "quant-factor-contribution.v2.2",
      "name": "relative_momentum_6m",
      "group": "relative",
      "symbol": "NVDA",
      "as_of": "2021-02-11T21:00:00Z",
      "availability_cutoff": "2021-02-11T21:00:00Z",
      "provenance": [
        "553984518adceebc897ac194bebbd62611a21811ac7fe16d39f46946ec7c2236",
        "synthetic-diagnostic:ENGINEERING_FIXTURE_NOT_REAL_MARKET_DATA"
      ],
      "lookback": 126,
      "raw": "-0.028068972513965818599597096",
      "normalized": "0.4080085290048998764605941690",
      "weight": "0.25",
      "contribution": "0.1020021322512249691151485422",
      "missing_reason": null,
      "transformation": "FIXED_SCALE_AND_BOUNDED_TIED_RANK_BLEND"
    },
    {
      "version": "quant-factor-contribution.v2.2",
      "name": "medium_distance",
      "group": "trend",
      "symbol": "NVDA",
      "as_of": "2021-02-11T21:00:00Z",
      "availability_cutoff": "2021-02-11T21:00:00Z",
      "provenance": [
        "553984518adceebc897ac194bebbd62611a21811ac7fe16d39f46946ec7c2236",
        "synthetic-diagnostic:ENGINEERING_FIXTURE_NOT_REAL_MARKET_DATA"
      ],
      "lookback": 60,
      "raw": "0.014642166459673867727791068",
      "normalized": "0.6141363710753921703893943049",
      "weight": "0.125",
      "contribution": "0.07676704638442402129867428811",
      "missing_reason": null,
      "transformation": "FIXED_SCALE_AND_BOUNDED_TIED_RANK_BLEND"
    },
    {
      "version": "quant-factor-contribution.v2.2",
      "name": "trend_persistence",
      "group": "trend",
      "symbol": "NVDA",
      "as_of": "2021-02-11T21:00:00Z",
      "availability_cutoff": "2021-02-11T21:00:00Z",
      "provenance": [
        "553984518adceebc897ac194bebbd62611a21811ac7fe16d39f46946ec7c2236",
        "synthetic-diagnostic:ENGINEERING_FIXTURE_NOT_REAL_MARKET_DATA"
      ],
      "lookback": 60,
      "raw": "0.0166666666666666666666666667",
      "normalized": "0.5449519230769230769230769231",
      "weight": "0.125",
      "contribution": "0.06811899038461538461538461539",
      "missing_reason": null,
      "transformation": "FIXED_SCALE_AND_BOUNDED_TIED_RANK_BLEND"
    }
  ],
  "signal_persistence": null,
  "regime": {
    "version": "quant-regime-v2.1",
    "as_of": "2021-02-11T21:00:00Z",
    "trend": "TRENDING_UP",
    "volatility": "HIGH_VOLATILITY",
    "drawdown_stress": false,
    "risk_multiplier": "0.5",
    "exposure_ceiling": "0.5",
    "rebalance_urgency": "RISK_REDUCTION",
    "input_hash": "7eae7da4789cd81f6d20515a37ff91f7614cac5057520193f8d9d6abf58a5a4b",
    "reasons": [
      "SPY_TREND_AND_TRAILING_VOLATILITY"
    ]
  },
  "regime_is_prediction": false,
  "preferred_exposure": "0.231430",
  "feasible_exposure": "0.083333",
  "current_exposure": null,
  "cost_adjusted_exposure": null,
  "concentration_effect": [
    "POSITION_COUNT_CAP_AND_SINGLE_INVERSE_VOLATILITY_SIZING",
    "SECTOR_EXPOSURE_CAP:SYNTHETIC_SECTOR",
    "FRESH_ACCOUNT_REQUIRED_NO_CURRENCY_COST_ESTIMATE"
  ],
  "decision_category": "WAIT_FOR_EVIDENCE",
  "price_condition": {
    "observed_price": "127.0632811719226998695736667",
    "quote_hash": "eddc26778755914c2cece4c89d6e11b91e018925e9897a5541d8d846e48c91e2",
    "observation_at": "2021-02-11T21:00:00+00:00",
    "timezone": "America/New_York",
    "quantitative_entry_zone": null,
    "method": null,
    "assumptions": [],
    "fair_value": null,
    "user_approved_executable_limit": null,
    "assessment": "WAIT_FOR_EVIDENCE",
    "invalidation_condition": "Recompute after a new completed session, corporate action or stale observation.",
    "reason": "Qualified ATR/price basis/current observation unavailable; no invented entry price."
  },
  "catalysts": "UNKNOWN：未提供带来源与时间的新闻或财务证据。",
  "gpt_interpretation": "UNKNOWN：模型未完成，保留定量证据。",
  "scenarios": "UNKNOWN：没有已验证的模型情景输出。",
  "opposing_evidence": [
    "FRESH_ACCOUNT_REQUIRED_NO_CURRENCY_COST_ESTIMATE",
    "PUBLIC_RETRIEVAL_AFTER_CUTOFF",
    "INSUFFICIENT_VERIFIED_HISTORY"
  ],
  "monitoring_trigger": "等待新鲜报价、可信复权历史与企业行动证据；按同一截止时点重新计算。",
  "invalidation_condition": "Recompute after a new completed session, corporate action or stale observation.",
  "no_action_reasons": [
    "FRESH_ACCOUNT_REQUIRED_NO_CURRENCY_COST_ESTIMATE",
    "INSUFFICIENT_VERIFIED_HISTORY",
    "PUBLIC_RETRIEVAL_AFTER_CUTOFF"
  ],
  "important_unknowns": [
    "内在价值",
    "新闻催化剂",
    "校准预期收益",
    "ETF 穿透重叠",
    "当前账户风险上下文"
  ],
  "manual_requirements": [
    "这是研究分类，不是券商订单。",
    "独立核对账户、报价和风险；真实订单逐笔人工批准。"
  ],
  "quant_engine": "V2.2_SHADOW",
  "gpt_engine": "GPT_ADVISORY",
  "predictive_confidence": null,
  "trade_authorized": false,
  "explanation": "NVDA：定量通道为 INSUFFICIENT_VERIFIED_HISTORY；当前报价状态 LIVE；研究分类 WAIT_FOR_EVIDENCE。缺失因子与价格条件保持 UNKNOWN，分数不代表获利概率。"
}
```

### UNKNOWN（名称未获核验） / SPY

SPY：定量通道为 INSUFFICIENT_VERIFIED_HISTORY；当前报价状态 LIVE；研究分类 WAIT_FOR_EVIDENCE。缺失因子与价格条件保持 UNKNOWN，分数不代表获利概率。

当前观察价：210.1079373378071409291537006；带日期参考价：210.1079373378071409291537006；时间：2021-02-11T16:00:00-05:00；来源：FIXTURE_ONLY；声明延迟：None。

```json
{
  "symbol": "SPY",
  "company": "UNKNOWN（名称未获核验）",
  "observed_price": "210.1079373378071409291537006",
  "dated_reference_price": "210.1079373378071409291537006",
  "observation_at": "2021-02-11T16:00:00-05:00",
  "timezone": "America/New_York",
  "provider": "FIXTURE_ONLY",
  "feed_delay_seconds": null,
  "history_quality": "INSUFFICIENT_VERIFIED_HISTORY",
  "momentum_3m": "0.065303023698422805084393694",
  "momentum_6m": "0.099462587756885690020017435",
  "relative_strength_6m": "0E-27",
  "trend_sma60": "205.0131662536433109258613427",
  "volatility_60": "0.06781483813512831836236952353",
  "drawdown_252": "-0.0207604015253966918686532426",
  "quant_score": null,
  "quant_rank": null,
  "factor_attribution": [
    {
      "version": "quant-factor-contribution.v2.2",
      "name": "momentum_3m",
      "group": "absolute",
      "symbol": "SPY",
      "as_of": "2021-02-11T21:00:00Z",
      "availability_cutoff": "2021-02-11T21:00:00Z",
      "provenance": [
        "7eae7da4789cd81f6d20515a37ff91f7614cac5057520193f8d9d6abf58a5a4b",
        "synthetic-diagnostic:ENGINEERING_FIXTURE_NOT_REAL_MARKET_DATA"
      ],
      "lookback": 63,
      "raw": "0.065303023698422805084393694",
      "normalized": "0.7108358045865026599846295056",
      "weight": "0.100",
      "contribution": "0.07108358045865026599846295056",
      "missing_reason": null,
      "transformation": "FIXED_SCALE_AND_BOUNDED_TIED_RANK_BLEND"
    },
    {
      "version": "quant-factor-contribution.v2.2",
      "name": "momentum_6m",
      "group": "absolute",
      "symbol": "SPY",
      "as_of": "2021-02-11T21:00:00Z",
      "availability_cutoff": "2021-02-11T21:00:00Z",
      "provenance": [
        "7eae7da4789cd81f6d20515a37ff91f7614cac5057520193f8d9d6abf58a5a4b",
        "synthetic-diagnostic:ENGINEERING_FIXTURE_NOT_REAL_MARKET_DATA"
      ],
      "lookback": 126,
      "raw": "0.099462587756885690020017435",
      "normalized": "0.7587519429013341675909106229",
      "weight": "0.150",
      "contribution": "0.1138127914352001251386365934",
      "missing_reason": null,
      "transformation": "FIXED_SCALE_AND_BOUNDED_TIED_RANK_BLEND"
    },
    {
      "version": "quant-factor-contribution.v2.2",
      "name": "momentum_12_1",
      "group": "absolute",
      "symbol": "SPY",
      "as_of": "2021-02-11T21:00:00Z",
      "availability_cutoff": "2021-02-11T21:00:00Z",
      "provenance": [
        "7eae7da4789cd81f6d20515a37ff91f7614cac5057520193f8d9d6abf58a5a4b",
        "synthetic-diagnostic:ENGINEERING_FIXTURE_NOT_REAL_MARKET_DATA"
      ],
      "lookback": 252,
      "raw": "0.185547929625581446220739403",
      "normalized": "0.8286556939691549740153974635",
      "weight": "0.250",
      "contribution": "0.2071639234922887435038493659",
      "missing_reason": null,
      "transformation": "FIXED_SCALE_AND_BOUNDED_TIED_RANK_BLEND"
    },
    {
      "version": "quant-factor-contribution.v2.2",
      "name": "relative_momentum_6m",
      "group": "relative",
      "symbol": "SPY",
      "as_of": "2021-02-11T21:00:00Z",
      "availability_cutoff": "2021-02-11T21:00:00Z",
      "provenance": [
        "7eae7da4789cd81f6d20515a37ff91f7614cac5057520193f8d9d6abf58a5a4b",
        "synthetic-diagnostic:ENGINEERING_FIXTURE_NOT_REAL_MARKET_DATA"
      ],
      "lookback": 126,
      "raw": "0E-27",
      "normalized": "0.528125",
      "weight": "0.25",
      "contribution": "0.13203125",
      "missing_reason": null,
      "transformation": "FIXED_SCALE_AND_BOUNDED_TIED_RANK_BLEND"
    },
    {
      "version": "quant-factor-contribution.v2.2",
      "name": "medium_distance",
      "group": "trend",
      "symbol": "SPY",
      "as_of": "2021-02-11T21:00:00Z",
      "availability_cutoff": "2021-02-11T21:00:00Z",
      "provenance": [
        "7eae7da4789cd81f6d20515a37ff91f7614cac5057520193f8d9d6abf58a5a4b",
        "synthetic-diagnostic:ENGINEERING_FIXTURE_NOT_REAL_MARKET_DATA"
      ],
      "lookback": 60,
      "raw": "0.024850945806380814729346597",
      "normalized": "0.6816776680608935697139765821",
      "weight": "0.125",
      "contribution": "0.08520970850761169621424707276",
      "missing_reason": null,
      "transformation": "FIXED_SCALE_AND_BOUNDED_TIED_RANK_BLEND"
    },
    {
      "version": "quant-factor-contribution.v2.2",
      "name": "trend_persistence",
      "group": "trend",
      "symbol": "SPY",
      "as_of": "2021-02-11T21:00:00Z",
      "availability_cutoff": "2021-02-11T21:00:00Z",
      "provenance": [
        "7eae7da4789cd81f6d20515a37ff91f7614cac5057520193f8d9d6abf58a5a4b",
        "synthetic-diagnostic:ENGINEERING_FIXTURE_NOT_REAL_MARKET_DATA"
      ],
      "lookback": 60,
      "raw": "0.05",
      "normalized": "0.620625",
      "weight": "0.125",
      "contribution": "0.077578125",
      "missing_reason": null,
      "transformation": "FIXED_SCALE_AND_BOUNDED_TIED_RANK_BLEND"
    }
  ],
  "signal_persistence": null,
  "regime": {
    "version": "quant-regime-v2.1",
    "as_of": "2021-02-11T21:00:00Z",
    "trend": "TRENDING_UP",
    "volatility": "HIGH_VOLATILITY",
    "drawdown_stress": false,
    "risk_multiplier": "0.5",
    "exposure_ceiling": "0.5",
    "rebalance_urgency": "RISK_REDUCTION",
    "input_hash": "7eae7da4789cd81f6d20515a37ff91f7614cac5057520193f8d9d6abf58a5a4b",
    "reasons": [
      "SPY_TREND_AND_TRAILING_VOLATILITY"
    ]
  },
  "regime_is_prediction": false,
  "preferred_exposure": "0.265779",
  "feasible_exposure": "0.100000",
  "current_exposure": null,
  "cost_adjusted_exposure": null,
  "concentration_effect": [
    "POSITION_COUNT_CAP_AND_SINGLE_INVERSE_VOLATILITY_SIZING",
    "SECTOR_EXPOSURE_CAP:SYNTHETIC_SECTOR",
    "FRESH_ACCOUNT_REQUIRED_NO_CURRENCY_COST_ESTIMATE"
  ],
  "decision_category": "WAIT_FOR_EVIDENCE",
  "price_condition": {
    "observed_price": "210.1079373378071409291537006",
    "quote_hash": "93a0284c10bd0d4219000c18dc46d2cb36f32a97308244b466519bc96a26b1bf",
    "observation_at": "2021-02-11T21:00:00+00:00",
    "timezone": "America/New_York",
    "quantitative_entry_zone": null,
    "method": null,
    "assumptions": [],
    "fair_value": null,
    "user_approved_executable_limit": null,
    "assessment": "WAIT_FOR_EVIDENCE",
    "invalidation_condition": "Recompute after a new completed session, corporate action or stale observation.",
    "reason": "Qualified ATR/price basis/current observation unavailable; no invented entry price."
  },
  "catalysts": "UNKNOWN：未提供带来源与时间的新闻或财务证据。",
  "gpt_interpretation": "UNKNOWN：模型未完成，保留定量证据。",
  "scenarios": "UNKNOWN：没有已验证的模型情景输出。",
  "opposing_evidence": [
    "FRESH_ACCOUNT_REQUIRED_NO_CURRENCY_COST_ESTIMATE",
    "PUBLIC_RETRIEVAL_AFTER_CUTOFF",
    "INSUFFICIENT_VERIFIED_HISTORY"
  ],
  "monitoring_trigger": "等待新鲜报价、可信复权历史与企业行动证据；按同一截止时点重新计算。",
  "invalidation_condition": "Recompute after a new completed session, corporate action or stale observation.",
  "no_action_reasons": [
    "FRESH_ACCOUNT_REQUIRED_NO_CURRENCY_COST_ESTIMATE",
    "INSUFFICIENT_VERIFIED_HISTORY",
    "PUBLIC_RETRIEVAL_AFTER_CUTOFF"
  ],
  "important_unknowns": [
    "内在价值",
    "新闻催化剂",
    "校准预期收益",
    "ETF 穿透重叠",
    "当前账户风险上下文"
  ],
  "manual_requirements": [
    "这是研究分类，不是券商订单。",
    "独立核对账户、报价和风险；真实订单逐笔人工批准。"
  ],
  "quant_engine": "V2.2_SHADOW",
  "gpt_engine": "GPT_ADVISORY",
  "predictive_confidence": null,
  "trade_authorized": false,
  "explanation": "SPY：定量通道为 INSUFFICIENT_VERIFIED_HISTORY；当前报价状态 LIVE；研究分类 WAIT_FOR_EVIDENCE。缺失因子与价格条件保持 UNKNOWN，分数不代表获利概率。"
}
```
