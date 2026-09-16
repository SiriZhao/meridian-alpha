from pathlib import Path

path = Path("src/meridian/application.py")
content = path.read_text(encoding="utf-8")
replacements = [
    (
        """        research_inputs_ready = bool(research_quotes) and all(
            quote.timestamp <= cutoff
            and 0 <= (cutoff - quote.timestamp).total_seconds()
            <= policies.data.research.maximum_market_age_seconds
            for quote in research_quotes.values()
        )
        eligible_research_tickers = tuple(
""",
        """        research_inputs_ready = bool(research_quotes) and all(
            quote.timestamp <= cutoff
            and 0 <= (cutoff - quote.timestamp).total_seconds()
            <= policies.data.research.maximum_market_age_seconds
            for quote in research_quotes.values()
        )
        expected_closed_market = (
            current_market.status is not MarketStatus.OPEN
            and market_error is None
            and research_inputs_ready
        )
        daily_data_status = (
            "PASS"
            if market_valid
            else "MARKET_CLOSED"
            if expected_closed_market
            else "FAILED"
        )
        eligible_research_tickers = tuple(
""",
    ),
    (
        """                        "status": "PASS" if market_valid else "BLOCKED",
                        "error_code": market_error
                        or (None if market_valid else "MARKET_INPUT_NOT_READY"),
                        "next_action": "Review provider probes and freshness.",
""",
        """                        "status": daily_data_status,
                        "error_code": market_error
                        or (
                            None
                            if market_valid or expected_closed_market
                            else "MARKET_INPUT_NOT_READY"
                        ),
                        "next_action": (
                            "Wait for the next regular session; completed-session data remains research-only."
                            if expected_closed_market
                            else "Review provider probes and freshness."
                        ),
""",
    ),
    (
        """                "data_status": "PASS"
                if quotes
                and not any("MARKET" in reason for reason in result.decision.blocked_reasons)
                else "FAILED",
""",
        """                "data_status": daily_data_status,
                "market_data_tradeable": (
                    current_market.status is MarketStatus.OPEN and market_valid
                ),
""",
    ),
    (
        """        report_status = str(daily.get("status", "FAILED"))
        research_status = str(daily.get("research_status", "NOT_RUN"))
""",
        """        report_status = str(daily.get("status", "FAILED"))
        data_status = str(daily.get("data_status", "FAILED"))
        research_status = str(daily.get("research_status", "NOT_RUN"))
""",
    ),
    (
        """        blockers: list[str] = []
        if str(daily.get("runtime_status", "FAILED")) != "PASS":
            blockers.append("PAPER_CANONICAL_RUNTIME_FAILED")
        if market_session != MarketStatus.OPEN.value:
            blockers.append("PAPER_EXECUTION_BLOCKED_MARKET_CLOSED")
        if str(daily.get("data_status", "FAILED")) != "PASS" or not quotes:
            blockers.append("PAPER_EXECUTION_BLOCKED_MARKET_DATA")
        if research_status != "AVAILABLE":
            blockers.append("PAPER_EXECUTION_BLOCKED_RESEARCH_" + research_status)
        if report_status not in {"DRAFT", "NO_ACTION"}:
            blockers.append("PAPER_EXECUTION_BLOCKED_DECISION_" + report_status)
        if report_status == "DRAFT" and not isinstance(targets, list):
            blockers.append("PAPER_EXECUTION_BLOCKED_DECISION_CONTEXT")

        execution_status = "PAPER_BLOCKED"
""",
        """        blockers: list[str] = []
        fatal_blockers: list[str] = []
        if str(daily.get("runtime_status", "FAILED")) != "PASS":
            fatal_blockers.append("PAPER_CANONICAL_RUNTIME_FAILED")
        if market_session != MarketStatus.OPEN.value:
            blockers.append("PAPER_EXECUTION_BLOCKED_MARKET_CLOSED")
        expected_closed_market = (
            market_session != MarketStatus.OPEN.value and data_status == "MARKET_CLOSED"
        )
        if (data_status != "PASS" or not quotes) and not expected_closed_market:
            fatal_blockers.append("PAPER_EXECUTION_BLOCKED_MARKET_DATA")
        if research_status != "AVAILABLE":
            fatal_blockers.append("PAPER_EXECUTION_BLOCKED_RESEARCH_" + research_status)
        expected_closed_decision = (
            expected_closed_market and report_status == RunStatus.BLOCKED_STALE_MARKET.value
        )
        if report_status not in {"DRAFT", "NO_ACTION"} and not expected_closed_decision:
            fatal_blockers.append("PAPER_EXECUTION_BLOCKED_DECISION_" + report_status)
        if report_status == "DRAFT" and not isinstance(targets, list):
            fatal_blockers.append("PAPER_EXECUTION_BLOCKED_DECISION_CONTEXT")
        blockers.extend(fatal_blockers)

        execution_status = (
            "PAPER_WAITING_FOR_MARKET"
            if expected_closed_market and not fatal_blockers
            else "PAPER_BLOCKED"
        )
""",
    ),
    (
        """        final_status = execution_status if execution_status != "PAPER_BLOCKED" else "PAPER_BLOCKED"
""",
        """        final_status = (
            "PAPER_READY" if execution_status == "PAPER_COMPLETE" else execution_status
        )
""",
    ),
    (
        """            "market": {
                "status": daily.get("data_status", "NOT_RUN"),
                "session": market_session,
                "observations": quotes,
""",
        """            "market": {
                "status": data_status,
                "session": market_session,
                "market_data_tradeable": bool(
                    daily.get(
                        "market_data_tradeable",
                        market_session == MarketStatus.OPEN.value and data_status == "PASS",
                    )
                ),
                "observations": quotes,
""",
    ),
]
for index, (old, new) in enumerate(replacements, 1):
    if old not in content:
        raise SystemExit(f"missing application block {index}")
    content = content.replace(old, new, 1)
path.write_text(content, encoding="utf-8")

test_path = Path("tests/test_execution_still_blocked_when_closed.py")
test = test_path.read_text(encoding="utf-8")
test_replacements = [
    (
        """        "data_status": "PASS",
""",
        """        "data_status": "MARKET_CLOSED",
        "market_data_tradeable": False,
""",
    ),
    (
        """    assert result["status"] == "PAPER_BLOCKED"
""",
        """    assert result["status"] == "PAPER_WAITING_FOR_MARKET"
""",
    ),
    (
        """    assert "PAPER_EXECUTION_BLOCKED_MARKET_CLOSED" in blockers
""",
        """    assert "PAPER_EXECUTION_BLOCKED_MARKET_CLOSED" in blockers
    assert result["market"]["market_data_tradeable"] is False
    assert result["paper_execution"]["fills"] == []
""",
    ),
]
for index, (old, new) in enumerate(test_replacements, 1):
    if old not in test:
        raise SystemExit(f"missing closed test block {index}")
    test = test.replace(old, new, 1)
test += """

def test_open_market_with_stale_data_remains_blocked(tmp_path: Path, monkeypatch) -> None:
    service = MeridianApplicationService(RuntimePaths(tmp_path / "runtime"))
    stale_daily = {
        "run_id": "daily-open-stale",
        "information_cutoff": "2026-09-08T14:00:00+00:00",
        "analysis_time": "2026-09-08T14:00:00+00:00",
        "trading_date": "2026-09-08",
        "status": "BLOCKED_STALE_MARKET",
        "runtime_status": "PASS",
        "data_status": "FAILED",
        "market_data_tradeable": False,
        "research_status": "AVAILABLE",
        "market_observations": {},
        "portfolio": None,
        "readiness": {},
        "manual_authority": {},
        "research": {"context": {"status": "AVAILABLE"}},
    }
    monkeypatch.setattr(service, "daily", lambda *args, **kwargs: stale_daily)
    result = service.paper_run()
    assert result["status"] == "PAPER_BLOCKED"
    assert "PAPER_EXECUTION_BLOCKED_MARKET_DATA" in result["blockers"]
    assert result["market"]["market_data_tradeable"] is False
    assert result["paper_execution"]["fills"] == []
"""
test_path.write_text(test, encoding="utf-8")

paper_test_path = Path("tests/test_paper_runtime.py")
paper_test = paper_test_path.read_text(encoding="utf-8")
old_assertion = '    assert first["status"] == "PAPER_COMPLETE"'
if old_assertion not in paper_test:
    raise SystemExit("missing paper runtime assertion")
paper_test_path.write_text(
    paper_test.replace(old_assertion, '    assert first["status"] == "PAPER_READY"', 1),
    encoding="utf-8",
)
