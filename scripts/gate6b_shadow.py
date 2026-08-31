"""Gate 6B five-equity real certified shadow observation.

The script delegates numeric certification to the existing SECCompanyFacts
lane and delegates alpha arithmetic to ProductionShadowOrchestrator.  Frozen
DeepSeek outputs are replayed only for their original decision cutoff.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from gate3b17_real_shadow import build_dislocation_screen, build_real_fundamentals

from meridian.authorization import EvidenceAuthorizationService
from meridian.config import AllocationPolicy, RiskPolicy
from meridian.evidence import ProviderCapabilities
from meridian.identity_certification import authoritative_count, load_verified_security_certificates
from meridian.orchestrator import ProductionShadowOrchestrator
from meridian.research import CertifiedEvidenceView, GroundedResearchSignal, ResearchContextPacket
from meridian.schemas import AccountSnapshot, AccountSyncState, EvidenceItem, FreshnessState

ROOT = Path(__file__).parents[1]
REPORTS = ROOT / "reports"
SECURITY = REPORTS / "gate4f-security-master.json"
DEEPSEEK = REPORTS / "gate3b17-real-shadow-v8.json"
QUANT = REPORTS / "gate3b12-real-shadow-v5.json"
TICKERS = ("AAPL", "MSFT", "NVDA", "META", "GOOGL")


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _account(as_of: datetime) -> AccountSnapshot:
    return AccountSnapshot(
        snapshot_id="gate6b-shadow-synthetic-50000", account_alias="shadow-synthetic",
        provider="manual-fixture", as_of=as_of, total_equity=Decimal("50000"), cash=Decimal("50000"),
        sync_state=AccountSyncState.SYNCED, freshness_state=FreshnessState.VERIFIED,
    )


def _policies() -> tuple[RiskPolicy, AllocationPolicy]:
    return (
        RiskPolicy(max_position_weight=Decimal("0.25"), max_sector_weight=Decimal("1"), min_cash_weight=Decimal("0.10"), max_daily_turnover=Decimal("1"), max_single_order_nav_percent=Decimal("0.25"), max_number_positions=10),
        AllocationPolicy(allocator_selection="deterministic_fallback", max_correlation_proxy_weight=Decimal("1")),
    )


def _replay_signals(fundamentals: dict[str, Any], deepseek: dict[str, Any]) -> tuple[dict[str, object], dict[str, str], dict[str, int], dict[str, str], datetime]:
    outcomes = {str(item.get("ticker")): item for item in deepseek.get("outcomes", []) if item.get("ticker") in TICKERS}
    available = [item for item in outcomes.values() if item.get("as_of")]
    cutoff = datetime.fromisoformat(str(available[0]["as_of"]).replace("Z", "+00:00")) if available else datetime.now(UTC)
    capability = ProviderCapabilities(provider_name="sec-edgar-accession-certified", supports_historical=True, supports_point_in_time=True, research_grade=True)
    signals: dict[str, object] = {}
    response_hashes: dict[str, str] = {}
    counts: dict[str, int] = {}
    statuses: dict[str, str] = {}
    for ticker in TICKERS:
        outcome = outcomes.get(ticker, {})
        payload = outcome.get("structured_payload")
        if outcome.get("status") != "AVAILABLE" or not isinstance(payload, dict):
            statuses[ticker] = str(outcome.get("reason") or outcome.get("status") or "ABSTAIN")
            continue
        try:
            signal_cutoff = datetime.fromisoformat(str(outcome["as_of"]).replace("Z", "+00:00"))
            items = tuple(EvidenceItem.model_validate(item) for item in fundamentals["tickers"][ticker]["evidence_items"])
            context = ResearchContextPacket(context_id=f"gate6b-{ticker.lower()}", ticker=ticker, as_of=signal_cutoff, created_at=signal_cutoff, items=items)
            view = CertifiedEvidenceView.from_context(context, provider_registry={capability.provider_name: capability}, clock=lambda as_of=signal_cutoff: as_of)
            grounded = GroundedResearchSignal(ticker=ticker, as_of=signal_cutoff, direction=str(payload["direction"]), conviction=Decimal(str(payload["conviction"])), thesis=str(payload.get("thesis") or payload.get("reason") or "Frozen certified research."), risks=tuple(str(risk) for risk in payload.get("risks", ())), cited_evidence_ids=tuple(str(item) for item in payload["cited_evidence_ids"]))
            signals[ticker] = EvidenceAuthorizationService().authorize(grounded, view.packet, provider_registry={capability.provider_name: capability})
            response_hashes[ticker] = _digest(payload)
            counts[ticker] = len(signals[ticker].evidence_ids)
            statuses[ticker] = "REPLAY_AVAILABLE"
        except Exception as error:  # noqa: BLE001 - explicit per-ticker degradation
            statuses[ticker] = f"REPLAY_REJECTED:{type(error).__name__}"
    return signals, response_hashes, counts, statuses, cutoff


def run() -> dict[str, Any]:
    now = datetime.now(UTC)
    fundamentals, _snapshots = build_real_fundamentals(now, TICKERS)
    deepseek = json.loads(DEEPSEEK.read_text(encoding="utf-8"))["deepseek"]
    prior_quant = json.loads(QUANT.read_text(encoding="utf-8"))
    quant_scores = {str(row["ticker"]): Decimal(str(row["quant_alpha"])) for row in prior_quant.get("rows", []) if row.get("ticker") in TICKERS}
    signals, response_hashes, evidence_counts, research_statuses, decision_as_of = _replay_signals(fundamentals, deepseek)
    risk_policy, allocation_policy = _policies()
    result = ProductionShadowOrchestrator().run(account_snapshot=_account(decision_as_of), run_id="gate6b-daily-shadow-v11", decision_as_of=decision_as_of, certified_signals=signals, quant_scores=quant_scores, policy_hash=_digest({"risk": risk_policy.model_dump(mode="json"), "allocation": allocation_policy.model_dump(mode="json")}), risk_policy=risk_policy, allocation_policy=allocation_policy, response_hashes=response_hashes, quant_inputs={ticker: {"source": "gate3b12-real-shadow-v5", "score": str(score)} for ticker, score in quant_scores.items()})
    decisions = {item.ticker: item for item in result.alpha_decisions}
    rows: list[dict[str, object]] = []
    for ticker in TICKERS:
        decision = decisions.get(ticker)
        if decision is None:
            rows.append({"ticker": ticker, "research_status": research_statuses.get(ticker, "ABSTAIN"), "quant_score": str(quant_scores.get(ticker, "UNAVAILABLE")), "status": "NO_CERTIFIED_SIGNAL"})
        else:
            rows.append({"ticker": ticker, "research_status": research_statuses.get(ticker), "quant_score": str(decision.quant_score), "quant_only_alpha": str(decision.quant_only_alpha), "llm_direction": decision.research_direction, "llm_conviction": str(decision.research_conviction), "research_modifier": str(decision.research_modifier), "combined_alpha": str(decision.final_alpha), "allocation_effect": "TARGET_PORTFOLIO", "certified_evidence_count": evidence_counts.get(ticker, 0), "evidence_ids": list(decision.evidence_ids), "response_artifact_hash": decision.response_artifact_hash, "quant_input_hash": decision.quant_input_hash, "policy_hash": decision.policy_hash})
    coverage: dict[str, object] = {}
    for ticker in TICKERS:
        entry = fundamentals.get("tickers", {}).get(ticker, {})
        snapshot = entry.get("snapshot", {}) if isinstance(entry, dict) else {}
        facts = entry.get("certified_numeric_facts", []) if isinstance(entry, dict) else []
        coverage[ticker] = {"certified_facts": len(facts), "canonical_metrics": sorted({str(item.get("canonical_metric")) for item in facts if item.get("canonical_metric")}), "comparables": len(snapshot.get("comparable_series", [])), "derived": len(snapshot.get("derived", [])), "missing_metrics": snapshot.get("missing_metrics", []), "ambiguous_concepts": snapshot.get("ambiguous_metrics", []), "restatement_status": snapshot.get("restatement_status"), "latest_accepted_filing": snapshot.get("latest_accession"), "quality_score": round(min(1.0, len(facts) / 20.0) * (1.0 if not snapshot.get("ambiguous_metrics") else 0.8), 4)}
    try:
        dislocation = build_dislocation_screen(now, TICKERS)
    except Exception as error:  # noqa: BLE001
        dislocation = {"status": "UNAVAILABLE", "error": type(error).__name__, "candidates": []}
    security = load_verified_security_certificates(SECURITY)
    before = {item.ticker: str(item.target_weight) for item in result.target_before_risk.positions}
    after = {item.ticker: str(item.target_weight) for item in result.target_after_risk.positions}
    directions = sorted({str(row.get("llm_direction")) for row in rows if row.get("llm_direction")})
    report: dict[str, Any] = {"schema_version": "gate6b.v1", "created_at": now.isoformat(), "decision_as_of": decision_as_of.isoformat(), "authorization": result.authorization, "coverage": coverage, "rows": rows, "directional_diversity": {"observed": directions, "abstain_count": sum(1 for row in rows if row.get("status") == "NO_CERTIFIED_SIGNAL"), "note": "Natural output; no rescaling or forced diversity."}, "dislocation": dislocation, "security": {"runtime_authoritative": authoritative_count(security), "artifact_valid": True}, "allocator": {"name": result.target_before_risk.allocator_name, "target_before_risk": before, "target_after_risk": after}, "reconciliation": {"status": result.reconciliation_status.value, "warnings": list(result.reconciliation_warnings)}, "llm": {"mode": "FROZEN_REPLAY_ONLY", "live_calls": 0, "certified_signals": len(signals)}, "warnings": ["SHADOW / NOT AUTHORIZED FOR ENTRY", "NO_BROKER", "NO_SCHWAB", "NO_REAL_ACCOUNT", "NO_REAL_ORDERS", "NEWS_MACRO_EXCLUDED_FROM_CERTIFIED_GROUNDING"]}
    report["content_hash"] = _digest(report)
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "gate6b-five-equity-fundamentals.json").write_text(json.dumps({"schema_version": "gate6b.fundamentals.v1", "created_at": now.isoformat(), "decision_as_of": now.isoformat(), "coverage": coverage, "source_report_hash": fundamentals.get("content_hash")}, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    (REPORTS / "gate6b-five-equity-fundamentals.md").write_text("# Gate 6B — Five-equity certified fundamentals\n\n| Ticker | Certified facts | Canonical metrics | Comparables | Derived | Quality | Latest filing |\n|---|---:|---:|---:|---:|---:|---|\n" + "\n".join(f"| {ticker} | {data['certified_facts']} | {len(data['canonical_metrics'])} | {data['comparables']} | {data['derived']} | {data['quality_score']} | {data['latest_accepted_filing']} |" for ticker, data in coverage.items()) + "\n\nAll values are exact-accession SEC acceptance-time facts; no news or macro data enters certified grounding.\n", encoding="utf-8")
    (REPORTS / "gate6b-daily-shadow-v11.json").write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    mobile = ["# Meridian Alpha — Gate 6B 移动端影子报告", "", "账户状态：合成 Host 账户；未连接真实账户", "市场环境：真实市场影子数据；执行报价未认证", "量化判断：使用真实量化影子分数", "认证基本面：AAPL/MSFT/NVDA/META/GOOGL 逐一报告", "AI研判：仅复用已验证 AAPL/NVDA 冻结输出；其余保持 ABSTAIN", "抄底观察：确定性预筛选；不自动下单", f"组合目标：{json.dumps(after, ensure_ascii=False)}", "风险：确定性风险覆盖和现金约束", "阻塞项：无真实 Host 输入、执行报价 TO_BE_SELECTED、FinRL-X 不可用", "", "SHADOW / NOT AUTHORIZED FOR ENTRY"]
    (REPORTS / "gate6b-daily-shadow-v11.md").write_text("\n".join(mobile) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True, default=str))
