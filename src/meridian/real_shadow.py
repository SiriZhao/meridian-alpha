"""Bounded real-data SHADOW daily pipeline.

This module exercises public Yahoo/SEC observations with a synthetic account,
without invoking live TradingAgents, DeepSeek, a broker, or an execution path.
Every real observation remains unverified/non-executable until supervised
provider and PIT certification is completed.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from time import perf_counter
from typing import Any

from meridian.allocation import DeterministicFallbackAllocator
from meridian.candidates import CandidateSelector, ResearchCandidateSet
from meridian.config import EvidenceCompletenessPolicy, EvidencePacketPolicy, ResearchBudgetPolicy
from meridian.evidence import (
    EvidenceCompletenessEvaluator,
    EvidencePacketBuilder,
    ProviderCapabilities,
)
from meridian.evidence_foundation import SECCompanyFactsProvider
from meridian.historical import (
    HistoricalBarSeries,
    YahooChartHistoricalProvider,
    generate_shadow_features,
)
from meridian.quotes import YahooChartQuoteProvider
from meridian.reconciliation import ReconciliationEngine
from meridian.research import (
    FakeGroundedResearchNormalizer,
    GraphResearchSummary,
    GroundedResearchStatus,
    PointInTimeStatus,
    ResearchEvidencePacket,
    ResearchStatus,
)
from meridian.risk import RiskEngine
from meridian.schemas import (
    AccountSnapshot,
    AccountSyncState,
    AlphaScore,
    EvidenceItem,
    EvidencePointInTimeStatus,
    FreshnessState,
)
from meridian.security_master import DEFAULT_SECURITY_MASTER, SecurityCertificationStatus


class YahooMarketEvidenceProvider:
    """Convert real Yahoo last-price observations into Meridian evidence."""

    provider_name = "yahoo-market"
    network_capable = True

    def __init__(self, quote_provider: YahooChartQuoteProvider | None = None) -> None:
        self.quote_provider = quote_provider or YahooChartQuoteProvider(DEFAULT_SECURITY_MASTER)
        self.capabilities = ProviderCapabilities(
            provider_name=self.provider_name,
            supports_live=True,
            supports_historical=True,
            supports_point_in_time=False,
            supports_last=True,
            supports_ohlcv=True,
            timestamp_semantics="Yahoo chart regularMarketTime; delay and historical availability unverified",
            requires_api_key=False,
            execution_grade=False,
            research_grade=False,
        )

    def get_evidence(self, ticker: str, as_of: datetime) -> tuple[EvidenceItem, ...]:
        quote = self.quote_provider.get_quote(ticker, as_of=as_of)
        return (
            EvidenceItem(
                ticker=ticker.upper(),
                provider=self.provider_name,
                source="yahoo-chart-public",
                observed_at=quote.observed_at,
                available_at=quote.available_at,
                retrieved_at=quote.retrieved_at,
                title=f"Yahoo chart last price ({quote.market_status.value})",
                document_id=f"{quote.provider_symbol}:{quote.observed_at.isoformat()}",
                content_hash=hashlib.sha256(
                    f"{quote.provider_symbol}|{quote.observed_at.isoformat()}|{quote.last}".encode()
                ).hexdigest(),
                evidence_type="market",
                summary=f"last={quote.last}; quality={quote.quality_status.value}",
                point_in_time_status=EvidencePointInTimeStatus.UNVERIFIED,
            ),
        )


def _account(as_of: datetime) -> AccountSnapshot:
    return AccountSnapshot(
        snapshot_id="real-shadow-synthetic-50000",
        account_alias="shadow-synthetic",
        provider="manual-fixture",
        as_of=as_of,
        total_equity=Decimal("50000"),
        cash=Decimal("50000"),
        holdings=(),
        sync_state=AccountSyncState.SYNCED,
        freshness_state=FreshnessState.VERIFIED,
    )


def _budget() -> ResearchBudgetPolicy:
    return ResearchBudgetPolicy(
        max_graph_tickers_per_run=3,
        max_parallel_graphs=1,
        max_graph_age_hours=72,
        always_review_existing_holdings=True,
        candidate_selection_mode="existing_then_order",
        minimum_quant_score=Decimal("-1"),
        existing_holding_review_policy="always",
    )


def _feature_context(series: HistoricalBarSeries, as_of: datetime) -> dict[str, object]:
    features, lineage = generate_shadow_features(series, as_of)
    daily_return = features.get("daily_return")
    sma20 = features.get("sma20")
    last_close = series.bars[-1].close if series.bars else None
    trend = (last_close / sma20 - Decimal("1")) if last_close is not None and sma20 else None
    context: dict[str, object] = {
        "feature_timestamp": series.bars[-1].available_at if series.bars else None,
        "momentum": daily_return,
        "trend": trend,
        "volatility": features.get("realized_volatility"),
        "volume_ratio": features.get("volume_ratio"),
        "lineage": lineage.model_dump(mode="json"),
    }
    return context


def _summary(ticker: str, as_of: datetime) -> GraphResearchSummary:
    return GraphResearchSummary(
        ticker=ticker,
        as_of=as_of,
        status=ResearchStatus.UNAVAILABLE,
        provider="tradingagents",
        model="not-invoked",
        framework_version="0.3.1",
        started_at=as_of,
        completed_at=as_of,
        warnings=("LIVE_TRADINGAGENTS_SKIPPED_BY_POLICY",),
        point_in_time_status=PointInTimeStatus.HISTORICAL_LIVE_CALL_FORBIDDEN,
        source_mode="UNAVAILABLE",
    )


def run_real_shadow_daily(
    *,
    as_of: datetime | None = None,
    tickers: Sequence[str] = ("AAPL", "MSFT", "NVDA"),
    output_json: Path | None = None,
    output_markdown: Path | None = None,
) -> dict[str, Any]:
    """Acquire bounded real public observations and emit a shadow report."""
    cutoff = as_of or datetime.now(UTC)
    if cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise ValueError("real shadow as_of must be timezone-aware")
    quote_provider = YahooChartQuoteProvider(DEFAULT_SECURITY_MASTER)
    history_provider = YahooChartHistoricalProvider(DEFAULT_SECURITY_MASTER)
    market_evidence = YahooMarketEvidenceProvider(quote_provider)
    sec_provider = SECCompanyFactsProvider()
    budget = _budget()
    raw_features: dict[str, Mapping[str, object]] = {}
    history_by_ticker: dict[str, HistoricalBarSeries] = {}
    quote_metadata: dict[str, dict[str, object]] = {}
    failures: list[dict[str, str]] = []
    for ticker in tuple(sorted({item.upper() for item in tickers}))[: budget.max_graph_tickers_per_run]:
        try:
            started = perf_counter()
            series = history_provider.get_series(
                ticker,
                cutoff.date() - timedelta(days=45),
                cutoff.date(),
                as_of=cutoff,
            )
            history_by_ticker[ticker] = series
            raw_features[ticker] = _feature_context(series, cutoff)
            quote = quote_provider.get_quote(ticker, as_of=cutoff)
            quote_metadata[ticker] = {
                "provider": quote.provider,
                "provider_symbol": quote.provider_symbol,
                "observed_at": quote.observed_at.isoformat(),
                "available_at": quote.available_at.isoformat(),
                "retrieved_at": quote.retrieved_at.isoformat(),
                "last": str(quote.last) if quote.last is not None else None,
                "bid": str(quote.bid) if quote.bid is not None else None,
                "ask": str(quote.ask) if quote.ask is not None else None,
                "quality_status": quote.quality_status.value,
                "market_status": quote.market_status.value,
                "latency_ms": round((perf_counter() - started) * 1000, 2),
            }
        except Exception as error:  # noqa: BLE001 - isolate each real ticker
            failures.append({"ticker": ticker, "stage": "market_or_history", "error": type(error).__name__})

    candidate_set: ResearchCandidateSet = CandidateSelector().build(
        tuple(raw_features), raw_features, cutoff, policy=budget
    )
    packet_builder = EvidencePacketBuilder(
        EvidencePacketPolicy(
            max_total_evidence_items=20,
            max_items_per_type=5,
            max_summary_characters_per_item=500,
        ),
        clock=lambda: cutoff,
    )
    packets: list[ResearchEvidencePacket] = []
    summaries: list[GraphResearchSummary] = []
    outcomes = []
    diagnostics: list[dict[str, object]] = []
    completeness = EvidenceCompletenessPolicy(
        minimum_total_items=1,
        minimum_distinct_sources=1,
        required_evidence_types=(),
        maximum_age_by_type={},
        minimum_point_in_time_quality=Decimal("1"),
    )
    normalizer = FakeGroundedResearchNormalizer()
    alpha_scores: list[AlphaScore] = []
    for candidate in candidate_set.candidates:
        ticker = candidate.ticker
        providers = (market_evidence, sec_provider)
        packet = packet_builder.gather(ticker, cutoff, providers)
        packets.append(packet)
        summary = _summary(ticker, cutoff)
        summaries.append(summary)
        outcome = normalizer.normalize(summary, packet, cutoff)
        outcomes.append(outcome)
        quality = EvidenceCompletenessEvaluator(completeness).evaluate(packet, cutoff)
        quant = candidate.quant_score
        alpha_scores.append(
            AlphaScore(
                ticker=ticker,
                score=quant,
                confidence=Decimal("0"),
                expected_direction="BULLISH" if quant > 0 else "NEUTRAL",
                risk_penalty=Decimal("0"),
                evidence_quality=Decimal("0"),
                model_source="real-shadow-quant-only",
            )
        )
        diagnostics.append(
            {
                "ticker": ticker,
                "quant_only_score": str(quant),
                "grounded_research_modifier": "0",
                "final_alpha": str(quant),
                "evidence_completeness": quality.model_dump(mode="json"),
                "evidence_sources": sorted({item.source for item in packet.items}),
                "research_direction": None,
                "research_conviction": None,
                "research_status": outcome.status.value,
                "risk_penalty": "0",
                "real_quote": quote_metadata.get(ticker),
                "history_bars": len(history_by_ticker.get(ticker, HistoricalBarSeries(canonical_asset_id="missing", canonical_symbol=ticker, provider="none", as_of=cutoff)).bars),
                "research_executable": False,
            }
        )
    target = DeterministicFallbackAllocator().allocate(alpha_scores, {}, _account(cutoff), _risk_policy())
    risk = RiskEngine().approve(target, _account(cutoff), "RISK_ON", _risk_policy())
    target_before_risk = {position.ticker: str(position.target_weight) for position in target.positions}
    target_after_risk = {position.ticker: str(position.target_weight) for position in risk.approved.positions}
    for diagnostic in diagnostics:
        ticker = str(diagnostic["ticker"])
        diagnostic["target_before_risk"] = target_before_risk.get(ticker, "0")
        diagnostic["target_after_risk"] = target_after_risk.get(ticker, "0")
    reconciliation = ReconciliationEngine().reconcile(_account(cutoff), risk.approved)
    report: dict[str, Any] = {
        "schema_version": "1",
        "created_at": datetime.now(UTC).isoformat(),
        "as_of": cutoff.isoformat(),
        "mode": "SHADOW_REAL_DATA",
        "authorization": "SHADOW / NOT AUTHORIZED FOR ENTRY",
        "account_data": "SYNTHETIC",
        "market_data": "REAL_SHADOW",
        "fundamentals": "REAL_SEC_UNVERIFIED" if any(item.evidence_type == "fundamental" for packet in packets for item in packet.items) else "UNAVAILABLE",
        "news": "UNAVAILABLE",
        "macro": "UNAVAILABLE",
        "security_master": "DEVELOPMENT_VERIFIED_FIXTURES; AUTHORITATIVE_PROMOTION_PENDING",
        "security_certification_counts": {
            status.value: sum(1 for record in DEFAULT_SECURITY_MASTER.all_records() if record.certification_status is status)
            for status in SecurityCertificationStatus
        },
        "candidate_selection": [candidate.model_dump(mode="json") for candidate in candidate_set.candidates],
        "deferred_candidates": [candidate.model_dump(mode="json") for candidate in candidate_set.deferred],
        "graph": "NOT_INVOKED",
        "graph_summaries": [summary.model_dump(mode="json") for summary in summaries],
        "evidence_packets": [packet.model_dump(mode="json") for packet in packets],
        "grounded_statuses": [outcome.status.value for outcome in outcomes],
        "diagnostics": diagnostics,
        "certified_signal_count": 0,
        "abstain_count": sum(1 for outcome in outcomes if outcome.status is not GroundedResearchStatus.AVAILABLE),
        "provider_failures": failures + [
            {"provider": status.split(":", 1)[0], "status": status}
            for packet in packets
            for status in packet.provider_statuses
            if ":FAILED:" in status
        ],
        "allocator": {"name": target.allocator_name, "positions": {position.ticker: str(position.target_weight) for position in risk.approved.positions}},
        "risk_violations": list(risk.violations),
        "reconciliation_status": reconciliation.status.value,
        "real_observations": quote_metadata,
        "warnings": [
            "REAL PUBLIC OBSERVATIONS; SHADOW ONLY",
            "SEC FUNDAMENTALS ARE NOT HISTORICAL-PIT CERTIFIED",
            "YAHOO QUOTES ARE LAST-ONLY AND NON-EXECUTION-GRADE",
            "LIVE NEWS/MACRO PROVIDERS NOT CONNECTED",
            "LIVE TRADINGAGENTS AND DEEPSEEK SKIPPED",
            "SHADOW / NOT AUTHORIZED FOR ENTRY",
        ],
    }
    report["content_hash"] = hashlib.sha256(json.dumps(report, sort_keys=True, default=str).encode()).hexdigest()
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")
    if output_markdown is not None:
        output_markdown.parent.mkdir(parents=True, exist_ok=True)
        output_markdown.write_text(_markdown(report), encoding="utf-8")
    return report


def _risk_policy() -> Any:
    from meridian.config import RiskPolicy

    return RiskPolicy(
        max_position_weight=Decimal("0.25"), max_sector_weight=Decimal("1"),
        min_cash_weight=Decimal("0.10"), max_daily_turnover=Decimal("1"),
        max_single_order_nav_percent=Decimal("0.25"), max_number_positions=10,
    )


def _markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# Meridian Alpha — Gate 3B.5 Real-Data Shadow Daily Run",
        "",
        f"Status: **{report['authorization']}**",
        f"Account: `{report['account_data']}`; market: `{report['market_data']}`; candidates: {len(report['candidate_selection'])}",
        f"ACCOUNT: `{report['account_data']}`",
        f"MARKET: `{report['market_data']}`",
        f"FUNDAMENTALS: `{report['fundamentals']}`",
        f"NEWS: `{report['news']}`",
        f"MACRO: `{report['macro']}`",
        "GRAPH: `NOT_INVOKED`",
        "NORMALIZER: `FAKE`",
        f"AUTHORIZATION: `{report['authorization']}`",
        f"Certified signals: {report['certified_signal_count']}; abstains/blocked: {report['abstain_count']}",
        "",
        "| Ticker | Quote quality | Bars | Research status | Evidence PIT |",
        "| --- | --- | ---: | --- | --- |",
    ]
    packets = {packet["ticker"]: packet for packet in report["evidence_packets"]}
    for item in report["diagnostics"]:
        packet = packets.get(item["ticker"], {})
        lines.append(
            f"| {item['ticker']} | {(item.get('real_quote') or {}).get('quality_status', 'UNAVAILABLE')} | {item['history_bars']} | {item['research_status']} | {packet.get('point_in_time_status', 'UNKNOWN')} |"
        )
    lines.extend(["", "Real observations are shadow-only. No live TradingAgents/DeepSeek request, broker call or order authorization occurred."])
    return "\n".join(lines) + "\n"
