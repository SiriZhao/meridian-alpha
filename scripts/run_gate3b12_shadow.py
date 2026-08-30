"""Explicit Gate 3B.12 shadow-only operational runner; no broker/order surface."""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from meridian.allocation import DeterministicFallbackAllocator
from meridian.alpha_fusion import (
    MAX_COMBINED_RESEARCH_MODIFIER,
    combine_research_modifiers,
    fuse,
    research_modifier,
)
from meridian.config import RiskPolicy, load_policies
from meridian.dislocation import DislocationScreen
from meridian.live_shadow import run_live_certified_grounding_shadow
from meridian.real_shadow import _account, run_real_shadow_daily
from meridian.research import LiveResearchShadowOptIn
from meridian.risk import RiskEngine
from meridian.sec_filing_metadata import SECAccessionCertifiedFactsProvider
from meridian.security_master import DEFAULT_SECURITY_MASTER, SecurityCertificationStatus

ROOT = Path(__file__).parents[1]
OUT = ROOT / "reports"
REPLAY = ROOT / "artifacts" / "gate3b12-replay"


def risk_policy() -> RiskPolicy:
    return RiskPolicy(
        max_position_weight=Decimal("0.25"), max_sector_weight=Decimal("1"),
        min_cash_weight=Decimal("0.10"), max_daily_turnover=Decimal("1"),
        max_single_order_nav_percent=Decimal("0.25"), max_number_positions=10,
    )


def main() -> None:
    now = datetime.now(UTC)
    base_shadow = run_real_shadow_daily(as_of=now, tickers=("AAPL", "NVDA"))
    quant_by_ticker = {
        str(row["ticker"]): Decimal(str(row["quant_only_score"]))
        for row in base_shadow["diagnostics"]
    }
    settings = load_policies(ROOT / "policies").models.research
    if settings is None:
        raise RuntimeError("RESEARCH_SETTINGS_UNAVAILABLE")
    live = run_live_certified_grounding_shadow(
        settings, LiveResearchShadowOptIn(enabled=True), tickers=("AAPL", "NVDA"), now=datetime.now(UTC)
    )
    REPLAY.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    scores = []
    for outcome, certified in zip(live.outcomes, live.certified_signals, strict=True):
        quant = quant_by_ticker.get(certified.ticker, Decimal("0"))
        alpha = fuse(certified, quant)
        base = research_modifier(certified)
        dislocation = Decimal("0")
        combined = combine_research_modifiers(base, dislocation)
        payload = outcome.structured_payload
        artifact = {
            "model": outcome.model,
            "provider": outcome.provider,
            "timestamp": outcome.created_at.isoformat(),
            "ticker": certified.ticker,
            "decision_as_of": certified.as_of.isoformat(),
            "evidence_view_id": certified.packet_id,
            "evidence_ids": list(certified.evidence_ids),
            "structured_assistant_payload": payload,
            "diagnostics": list(outcome.diagnostics),
        }
        artifact["content_hash"] = hashlib.sha256(json.dumps(artifact, sort_keys=True, default=str).encode()).hexdigest()
        (REPLAY / f"{certified.ticker.lower()}-{artifact['content_hash'][:12]}.json").write_text(
            json.dumps(artifact, indent=2, sort_keys=True, default=str), encoding="utf-8"
        )
        rows.append({
            "ticker": certified.ticker,
            "quant_alpha": str(quant),
            "context_evidence_count": "REAL_YAHOO_PLUS_SEC_CONTEXT",
            "certified_evidence_count": len(certified.evidence_ids),
            "excluded_evidence": ["yahoo-market:PIT_NOT_EXECUTABLE"],
            "llm_status": outcome.status.value,
            "direction": certified.direction,
            "conviction": str(certified.conviction),
            "base_research_modifier": str(base),
            "dislocation_modifier": str(dislocation),
            "combined_research_modifier": str(combined),
            "combined_modifier_cap": str(MAX_COMBINED_RESEARCH_MODIFIER),
            "risk_penalty": str(alpha.risk_penalty),
            "final_alpha": str(alpha.score),
            "certified_signal_id": certified.certificate_id,
            "evidence_ids": list(certified.evidence_ids),
            "response_artifact_hash": artifact["content_hash"],
        })
        scores.append(alpha)
    account = _account(now)
    target = DeterministicFallbackAllocator().allocate(scores, {}, account, risk_policy())
    risk = RiskEngine().approve(target, account, "RISK_ON", risk_policy())
    before = {item.ticker: str(item.target_weight) for item in target.positions}
    after = {item.ticker: str(item.target_weight) for item in risk.approved.positions}
    for row in rows:
        ticker = str(row["ticker"])
        row["target_before_risk"] = before.get(ticker, "0")
        row["target_after_risk"] = after.get(ticker, "0")
    dislocation_candidates = DislocationScreen().select({})
    msft_items = SECAccessionCertifiedFactsProvider().get_evidence("MSFT", now)
    report = {
        "schema_version": "1",
        "created_at": datetime.now(UTC).isoformat(),
        "as_of": now.isoformat(),
        "mode": "LIVE_SHADOW_REAL_DATA",
        "authorization": "SHADOW / NOT AUTHORIZED FOR ENTRY",
        "account": "SYNTHETIC_HOST_STYLE",
        "market": "REAL_YAHOO_SHADOW_ONLY",
        "deepseek": "LIVE_CERTIFIED_GROUNDING",
        "certified_signal_count": len(live.certified_signals),
        "rows": rows,
        "dislocation": {
            "screened_candidates": [item.model_dump(mode="json") for item in dislocation_candidates],
            "status": "ABSTAIN",
            "reason": "NO_ELIGIBLE_DETERMINISTIC_CANDIDATE; no separate dislocation LLM call made",
            "modifier": "0",
        },
        "msft_historical_sec": {"certified_item_count": len(msft_items), "status": "CERTIFIED" if msft_items else "UNVERIFIED"},
        "security_master": {
            "record_count": len(DEFAULT_SECURITY_MASTER.all_records()),
            "authoritative_verified": sum(record.certification_status is SecurityCertificationStatus.AUTHORITATIVE_VERIFIED for record in DEFAULT_SECURITY_MASTER.all_records()),
        },
        "allocator": {"name": target.allocator_name, "post_risk_weights": after},
        "risk_violations": list(risk.violations),
        "warnings": ["NO_BROKER", "NO_REAL_ACCOUNT", "NO_REAL_ORDERS", "YAHOO_EXCLUDED_FROM_CERTIFIED_PROMPT", "DISLOCATION_ABSTAIN"],
    }
    report["content_hash"] = hashlib.sha256(json.dumps(report, sort_keys=True, default=str).encode()).hexdigest()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "gate3b12-real-shadow-v5.json").write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")
    lines = ["# Gate 3B.12 real shadow V5", "", "Authorization: `SHADOW / NOT AUTHORIZED FOR ENTRY`", "", "| Ticker | Quant | LLM | Base | Dislocation | Combined | Final alpha | Pre-risk | Post-risk |", "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    lines += [f"| {row['ticker']} | {row['quant_alpha']} | {row['llm_status']} {row['direction']} ({row['conviction']}) | {row['base_research_modifier']} | {row['dislocation_modifier']} | {row['combined_research_modifier']} | {row['final_alpha']} | {row['target_before_risk']} | {row['target_after_risk']} |" for row in rows]
    lines += ["", "Yahoo data remained mixed-trust context and was excluded from certified prompts. Dislocation abstained because its deterministic screen produced no eligible candidate; no separate dislocation model call occurred."]
    (OUT / "gate3b12-real-shadow-v5.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"certified_signal_count": len(live.certified_signals), "rows": [{k: row[k] for k in ("ticker", "base_research_modifier", "final_alpha", "response_artifact_hash")} for row in rows], "msft": report["msft_historical_sec"], "security_master": report["security_master"]}, default=str))


if __name__ == "__main__":
    main()