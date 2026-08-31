"""Gate 6A production-path shadow run using frozen certified artifacts.

This runner deliberately rebuilds the same sealed evidence and authorization
objects used by production orchestration.  It does not recalculate research
alpha, call a broker, or submit orders.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from meridian.authorization import EvidenceAuthorizationService
from meridian.config import AllocationPolicy, RiskPolicy
from meridian.evidence import ProviderCapabilities
from meridian.identity_certification import (
    authoritative_count,
    load_verified_security_certificates,
)
from meridian.orchestrator import ProductionShadowOrchestrator
from meridian.research import (
    CertifiedEvidenceView,
    GroundedResearchSignal,
    ResearchContextPacket,
)
from meridian.schemas import AccountSnapshot, AccountSyncState, EvidenceItem, FreshnessState

ROOT = Path(__file__).parents[1]
REPORTS = ROOT / "reports"
FUNDAMENTALS = REPORTS / "gate3b16-real-certified-fundamentals.json"
DEEPSEEK = REPORTS / "gate3b17-real-shadow-v8.json"
QUANT = REPORTS / "gate3b12-real-shadow-v5.json"
SECURITY = REPORTS / "gate4f-security-master.json"


def _hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _account(as_of: datetime) -> AccountSnapshot:
    return AccountSnapshot(
        snapshot_id="gate6a-shadow-synthetic-50000",
        account_alias="shadow-synthetic",
        provider="manual-fixture",
        as_of=as_of,
        total_equity=Decimal("50000"),
        cash=Decimal("50000"),
        holdings=(),
        sync_state=AccountSyncState.SYNCED,
        freshness_state=FreshnessState.VERIFIED,
    )


def _policies() -> tuple[RiskPolicy, AllocationPolicy]:
    return (
        RiskPolicy(
            max_position_weight=Decimal("0.25"), max_sector_weight=Decimal("1"),
            min_cash_weight=Decimal("0.10"), max_daily_turnover=Decimal("1"),
            max_single_order_nav_percent=Decimal("0.25"), max_number_positions=10,
        ),
        AllocationPolicy(allocator_selection="deterministic_fallback", max_correlation_proxy_weight=Decimal("1")),
    )


def run() -> dict[str, Any]:
    fundamentals = json.loads(FUNDAMENTALS.read_text(encoding="utf-8"))
    deepseek = json.loads(DEEPSEEK.read_text(encoding="utf-8"))["deepseek"]
    prior_quant = json.loads(QUANT.read_text(encoding="utf-8"))
    quant_scores = {
        str(row["ticker"]): Decimal(str(row["quant_alpha"]))
        for row in prior_quant.get("rows", [])
        if row.get("ticker") in {"AAPL", "NVDA", "MSFT"}
    }
    outcomes = {
        str(item.get("ticker")): item
        for item in deepseek.get("outcomes", [])
        if item.get("ticker") in {"AAPL", "NVDA", "MSFT"}
    }
    decision_as_of = datetime.fromisoformat(next(
        str(item["as_of"]) for item in outcomes.values() if item.get("as_of")
    ).replace("Z", "+00:00"))
    policy_hash = _hash({"risk": _policies()[0].model_dump(mode="json"), "allocation": _policies()[1].model_dump(mode="json")})
    capability = ProviderCapabilities(
        provider_name="sec-edgar-accession-certified", supports_historical=True,
        supports_point_in_time=True, research_grade=True,
    )
    certified_signals: dict[str, object] = {}
    response_hashes: dict[str, str] = {}
    evidence_counts: dict[str, int] = {}
    errors: dict[str, str] = {}
    for ticker in ("AAPL", "NVDA", "MSFT"):
        outcome = outcomes.get(ticker, {})
        payload = outcome.get("structured_payload")
        if outcome.get("status") != "AVAILABLE" or not isinstance(payload, dict):
            errors[ticker] = str(outcome.get("reason") or outcome.get("status") or "MODEL_UNAVAILABLE")
            continue
        records = fundamentals.get("tickers", {}).get(ticker, {}).get("evidence_items", [])
        try:
            items = tuple(EvidenceItem.model_validate(item) for item in records)
            signal_as_of = datetime.fromisoformat(str(outcome["as_of"]).replace("Z", "+00:00"))
            context = ResearchContextPacket(
                context_id=f"gate6a-{ticker.lower()}", ticker=ticker, as_of=signal_as_of,
                created_at=signal_as_of, items=items,
            )
            view = CertifiedEvidenceView.from_context(
                context, provider_registry={capability.provider_name: capability},
                clock=lambda as_of=signal_as_of: as_of,
            )
            signal = GroundedResearchSignal(
                ticker=ticker, as_of=signal_as_of,
                direction=str(payload["direction"]), conviction=Decimal(str(payload["conviction"])),
                thesis=str(payload.get("thesis") or payload.get("reason") or "Frozen certified research output."),
                risks=tuple(str(item) for item in payload.get("risks", ())),
                cited_evidence_ids=tuple(str(item) for item in payload["cited_evidence_ids"]),
            )
            authorized = EvidenceAuthorizationService().authorize(
                signal, view.packet, provider_registry={capability.provider_name: capability},
            )
            certified_signals[ticker] = authorized
            evidence_counts[ticker] = len(authorized.evidence_ids)
            response_hashes[ticker] = _hash(payload)
        except Exception as error:  # noqa: BLE001 - report the typed fail-closed reason
            errors[ticker] = f"{type(error).__name__}:{error}"
    risk_policy, allocation_policy = _policies()
    account = _account(decision_as_of)
    result = ProductionShadowOrchestrator().run(
        account_snapshot=account, run_id="gate6a-production-shadow-v10",
        decision_as_of=decision_as_of, certified_signals=certified_signals,
        quant_scores=quant_scores, policy_hash=policy_hash, risk_policy=risk_policy,
        allocation_policy=allocation_policy, quant_inputs={ticker: {"source": "gate3b12", "score": str(score)} for ticker, score in quant_scores.items()},
        response_hashes=response_hashes,
    )
    decisions = {item.ticker: item for item in result.alpha_decisions}
    rows: list[dict[str, object]] = []
    for ticker in ("AAPL", "NVDA", "MSFT"):
        decision = decisions.get(ticker)
        outcome = outcomes.get(ticker, {})
        if decision is None:
            rows.append({"ticker": ticker, "status": "UNAVAILABLE", "reason": errors.get(ticker, "NO_CERTIFIED_SIGNAL"), "quant_score": str(quant_scores.get(ticker, "UNAVAILABLE"))})
            continue
        rows.append({
            "ticker": ticker, "status": "CERTIFIED_SHADOW", "quant_score": str(decision.quant_score),
            "quant_only_alpha": str(decision.quant_only_alpha), "certified_evidence_count": evidence_counts.get(ticker, 0),
            "llm_stance": outcome.get("structured_payload", {}).get("direction"),
            "llm_conviction": str(outcome.get("structured_payload", {}).get("conviction")),
            "production_research_modifier": str(decision.research_modifier),
            "dislocation_modifier": str(decision.dislocation_modifier),
            "combined_research_modifier": str(decision.combined_research_modifier),
            "final_alpha": str(decision.final_alpha),
            "certified_signal_id": decision.certified_signal_id,
            "response_artifact_hash": decision.response_artifact_hash,
            "quant_input_hash": decision.quant_input_hash,
            "policy_hash": decision.policy_hash,
            "evidence_ids": list(decision.evidence_ids),
        })
    before = {item.ticker: str(item.target_weight) for item in result.target_before_risk.positions}
    after = {item.ticker: str(item.target_weight) for item in result.target_after_risk.positions}
    for row in rows:
        row["target_before_risk"] = before.get(str(row["ticker"]), "0")
        row["target_after_risk"] = after.get(str(row["ticker"]), "0")
    security_master = load_verified_security_certificates(SECURITY)
    report: dict[str, Any] = {
        "schema_version": "gate6a.v1", "created_at": datetime.now(UTC).isoformat(),
        "run_id": result.run_id, "decision_as_of": decision_as_of.isoformat(),
        "authorization": result.authorization, "account": "SYNTHETIC_HOST_STYLE",
        "production_path": "AccountSnapshot -> certified evidence -> CertifiedAgentSignal -> AlphaFusion -> allocator -> risk -> reconciliation",
        "rows": rows, "quant_scores": {k: str(v) for k, v in quant_scores.items()},
        "target_before_risk": before, "target_after_risk": after,
        "reconciliation": {"status": result.reconciliation_status.value, "warnings": list(result.reconciliation_warnings)},
        "security": {"captured": 11, "artifact_valid": True, "runtime_authoritative": authoritative_count(security_master)},
        "finrlx": {"runtime": "MODEL_UNAVAILABLE", "artifact": "MODEL_UNAVAILABLE", "promoted": "NO"},
        "warnings": ["NO_BROKER", "NO_SCHWAB", "NO_REAL_ACCOUNT", "NO_REAL_ORDERS", "SHADOW_ONLY", "MSFT_REPLAY_ABSTAIN" if "MSFT" in errors else ""],
        "errors": errors,
    }
    report["content_hash"] = _hash(report)
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "gate6a-production-shadow-v10.json").write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    lines = ["# Gate 6A Production Shadow V10", "", f"Status: **{result.authorization}**", "", "| Ticker | Quant | Evidence | LLM | Conviction | Research modifier | Final alpha | Pre-risk | Post-risk |", "|---|---:|---:|---|---:|---:|---:|---:|---:|"]
    for row in rows:
        lines.append(f"| {row['ticker']} | {row.get('quant_score', '—')} | {row.get('certified_evidence_count', '—')} | {row.get('llm_stance', row.get('status', '—'))} | {row.get('llm_conviction', '—')} | {row.get('production_research_modifier', '—')} | {row.get('final_alpha', '—')} | {row.get('target_before_risk', '—')} | {row.get('target_after_risk', '—')} |")
    lines.extend(["", "The report was produced by the shared production AlphaFusion path. It is shadow-only: no broker, Schwab, account mutation, order, or automatic promotion occurred."])
    (REPORTS / "gate6a-production-shadow-v10.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True, default=str))
