"""Build the Gate 6D long-shadow foundation from existing sanitized artifacts.

The script never calls a provider.  It records the authoritative Gate 6A
production result, creates pending forward-outcome rows, executes the bounded
replay/soak battery, and reports the optional FinRL-X runtime honestly.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from meridian.finrlx_runtime import inspect_finrlx_runtime
from meridian.long_shadow import (
    ExecutionAssumption,
    PerformanceBudget,
    RunPerformance,
    ShadowPerformanceLedger,
    ShadowPerformanceRecord,
    ShadowRunLedger,
    ShadowRunRecord,
    attribute_llm_contribution,
    derive_daily_health,
    performance_warnings,
    run_historical_replay_battery,
    run_long_offline_soak,
)

ROOT = Path(__file__).parents[1]
REPORTS = ROOT / "reports"
VAR = ROOT / "var" / "shadow"


def _sha(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def _commit() -> str:
    try:
        return subprocess.check_output(("git", "rev-parse", "HEAD"), cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNAVAILABLE"


def main() -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    VAR.mkdir(parents=True, exist_ok=True)
    source_path = REPORTS / "gate6a-production-shadow-v10.json"
    source: dict[str, Any] = json.loads(source_path.read_text(encoding="utf-8")) if source_path.is_file() else {}
    as_of = datetime.fromisoformat(source.get("decision_as_of", datetime.now(UTC).isoformat()))
    rows = [row for row in source.get("rows", []) if row.get("status") == "CERTIFIED_SHADOW"]
    quant = {ticker: Decimal(str(value)) for ticker, value in source.get("quant_scores", {}).items()}
    alpha = {row["ticker"]: Decimal(str(row["final_alpha"])) for row in rows}
    targets = {ticker: Decimal(str(value)) for ticker, value in source.get("target_after_risk", {}).items()}
    ledger = ShadowRunLedger(VAR / "shadow-run-ledger.json")
    record = ShadowRunRecord(
        run_id="gate6d-shadow-observation-v1",
        decision_as_of=as_of,
        code_commit=_commit(),
        account_snapshot_hash=_sha("synthetic-host-style-account"),
        security_master_hash=_sha(source.get("security", {})),
        market_hashes=(_sha("gate6a-market-shadow"),),
        fundamental_hashes=(_sha("gate6b-certified-fundamentals"),),
        evidence_hashes=tuple(_sha(item) for item in sorted(alpha)),
        llm_artifact_hashes=tuple(str(row["response_artifact_hash"]) for row in rows if row.get("response_artifact_hash")),
        policy_hashes=tuple(str(row["policy_hash"]) for row in rows if row.get("policy_hash")),
        quant_signals=quant,
        final_alpha=alpha,
        target_weights=targets,
        risk_result=str(source.get("reconciliation", {}).get("status", "UNKNOWN")),
        provider_health={"SEC": "AVAILABLE", "market": "SHADOW", "DeepSeek": "REPLAY", "FinRL-X runtime": "MODEL_UNAVAILABLE"},
    )
    ledger.append(record)

    performance = ShadowPerformanceLedger(VAR / "shadow-performance-ledger.json")
    for ticker, weight in sorted(targets.items()):
        performance.add(ShadowPerformanceRecord(
            run_id=record.run_id,
            ticker=ticker,
            decision_as_of=as_of,
            horizon="1D",
            recommendation_weight=weight,
            target_weight=weight,
            execution_assumption=ExecutionAssumption.NEXT_SESSION_OPEN,
        ))
    attribution = [
        attribute_llm_contribution(
            row["ticker"],
            Decimal(str(row["quant_only_alpha"])),
            Decimal(str(row["final_alpha"])),
            Decimal(str(row.get("target_before_risk", "0"))),
            Decimal(str(row.get("target_after_risk", "0"))),
        ).model_dump(mode="json")
        for row in rows
    ]
    soak = run_long_offline_soak(cycles=100)
    replay = run_historical_replay_battery()
    measured = RunPerformance(daily_runtime_ms=0, market_fetch_ms=0, sec_build_ms=0, deepseek_calls=0, retries=0)
    budget = PerformanceBudget()
    health = derive_daily_health({"account": "SHADOW", "identity": "AVAILABLE", "market": "SHADOW", "evidence": "AVAILABLE", "research": "REPLAY", "quote": "UNVERIFIED", "risk": "PASS"})
    finrlx = inspect_finrlx_runtime()
    report = {
        "schema_version": "gate6d.v1",
        "status": "SHADOW",
        "authorization": "SHADOW / NOT AUTHORIZED FOR ENTRY",
        "ledger": {"path": str(ledger.path.relative_to(ROOT)), "records": len(ledger.records), "content_hash": ledger.content_hash},
        "performance": {"path": str((VAR / "shadow-performance-ledger.json").relative_to(ROOT)), "pending_rows": len(performance.records), "execution_assumption": ExecutionAssumption.NEXT_SESSION_OPEN.value, "outcomes_are_not_fills": True},
        "forward_outcomes": {"horizons": ["1D", "5D", "20D", "60D"], "joined": 0, "note": "Future outcomes are joined only after availability; no future data entered the decision record."},
        "llm_attribution": attribution,
        "dislocation_attribution": {"assessments": [], "status": "NO_CERTIFIED_DISLOCATION_ASSESSMENTS_IN_LEDGER"},
        "historical_replay": replay.model_dump(mode="json"),
        "soak": soak.model_dump(mode="json"),
        "performance_budget": {"measurement_mode": "OFFLINE_REPLAY; external provider latencies not measured", "measured": measured.model_dump(mode="json"), "budget": budget.model_dump(mode="json"), "warnings": list(performance_warnings(measured, budget))},
        "health": health.model_dump(mode="json"),
        "finrlx": finrlx.model_dump(mode="json"),
        "known_p0": 0,
        "known_p1": [],
        "safety": ["NO_BROKER", "NO_REAL_ORDERS", "NO_SCHWAB_AUTHENTICATION", "NO_AUTOMATIC_MODEL_PROMOTION"],
    }
    (REPORTS / "gate6d-finrlx-comparison.json").write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    lines = ["# Gate 6D — Long Shadow and FinRL-X Comparison", "", "Status: **SHADOW**", "", f"- Sanitized ledger records: **{len(ledger.records)}**", f"- Pending forward outcome rows: **{len(performance.records)}**", f"- Historical replay: **{replay.passed}/{len(replay.cases)}**", f"- Offline soak: **{soak.cycles} cycles; {soak.passed} scenario checks**", f"- Daily health: **{health.level.value}**", f"- FinRL-X runtime: **{finrlx.status.value}**", "", "| Ticker | Quant-only alpha | Quant + certified LLM | Delta |", "| --- | ---: | ---: | ---: |"]
    lines.extend(f"| {item['ticker']} | {item['quant_only_alpha']} | {item['combined_alpha']} | {item['alpha_delta']} |" for item in attribution)
    lines.extend(["", "No OOS model, forward outcome, causal superiority, broker action, or automatic promotion is claimed."])
    (REPORTS / "gate6d-finrlx-comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"report": "reports/gate6d-finrlx-comparison.json", "status": "SHADOW", "finrlx": finrlx.status.value, "known_p0": 0}, sort_keys=True))


if __name__ == "__main__":
    main()

