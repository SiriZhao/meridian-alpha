"""One-call, opt-in smoke test for the ChatGPT-managed Codex CLI provider."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from meridian.codex_provider import CodexCliProvider
from meridian.config import load_policies
from meridian.daily_research import DailyResearchInput, PublicResearchObservation
from meridian.runtime import policy_directory


def main() -> int:
    configured = load_policies(policy_directory()).models.research
    if configured is None:
        print(json.dumps({"status": "BLOCKED", "error": "CODEX_CONFIG_INVALID"}))
        return 2
    settings = configured.model_copy(
        update={"live_enabled": True, "llm_max_retries": 0}
    )
    now = datetime.now(UTC)
    request = DailyResearchInput(
        parent_run_id="codex-provider-smoke",
        analysis_cutoff=now,
        mode="LIVE",
        snapshot_reference="SMOKE_NO_ACCOUNT_DATA",
        market_reference="SMOKE_PUBLIC_FIXTURE",
        policy_reference="SMOKE_POLICY",
        provider=settings.provider,
        model=settings.model,
        observations=(
            PublicResearchObservation(
                ticker="AAPL",
                observed_at=now - timedelta(seconds=1),
                price=Decimal("100"),
                daily_return=Decimal("0.01"),
                reference="a" * 64,
            ),
        ),
        freshness_status="PASS",
        provider_provenance={"AAPL": "OPT_IN_SMOKE_FIXTURE"},
    )
    result = CodexCliProvider().run(request, settings)
    response = result.response
    payload = {
        "status": "PASS"
        if response is not None and result.diagnostics.schema_valid
        else "BLOCKED",
        "provider": result.diagnostics.provider,
        "auth_mode": result.diagnostics.auth_mode,
        "model_requested": result.diagnostics.model_requested,
        "reasoning_effort": result.diagnostics.reasoning_effort,
        "elapsed_ms": result.diagnostics.elapsed_ms,
        "exit_code": result.diagnostics.exit_code,
        "schema_valid": result.diagnostics.schema_valid,
        "research_status": response.status if response is not None else "NO_ACTION",
        "recommended_action": (
            response.recommended_action if response is not None else "NO_ACTION"
        ),
        "error_class": result.diagnostics.error_class,
        "attempts": result.attempts,
        "input_packet_hash": result.diagnostics.input_packet_hash,
        "output_hash": result.diagnostics.output_hash,
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if payload["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
