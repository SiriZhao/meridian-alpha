"""LEGACY / DEPRECATED TradingAgents research adapter.

The adapter deliberately exposes only Meridian's normalized research contract.
TradingAgents (and its OpenAI-compatible transport dependency) never crosses
into deterministic sizing, risk, reconciliation, or order planning.

It is not configured or installed by the Codex-native production runtime.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import importlib.util
import json
import os
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from pydantic import BaseModel, ConfigDict

from meridian.config import ResearchBudgetPolicy, ResearchSettings
from meridian.research import (
    GraphResearchSummary,
    PointInTimeStatus,
    ResearchMode,
    ResearchOutcome,
    ResearchStatus,
    normalize_signal,
)
from meridian.schemas import EvidenceItem

PINNED_TRADINGAGENTS_VERSION = "0.3.1"
PINNED_TRADINGAGENTS_COMMIT = "01477f9afb7a47b849ed4c9259d3a9a4738d9fda"
DEEPSEEK_ENDPOINT = "https://api.deepseek.com"

Runner = Callable[[str, datetime, dict[str, object], ResearchSettings], object]
GraphRunner = Callable[[str, datetime, dict[str, object], ResearchSettings], object]


class _StructuredResearchResult(BaseModel):
    """Small schema used with TradingAgents' native structured-output client."""

    model_config = ConfigDict(extra="allow")

    direction: str
    conviction: Decimal
    fundamental_score: Decimal | None = None
    technical_score: Decimal | None = None
    sentiment_score: Decimal | None = None
    news_score: Decimal | None = None
    risk_score: Decimal | None = None
    thesis: str
    risks: tuple[str, ...] = ()
    evidence: tuple[EvidenceItem, ...]


def _installed_version() -> str | None:
    try:
        return importlib.metadata.version("tradingagents")
    except importlib.metadata.PackageNotFoundError:
        return None


def _official_structured_runner(
    ticker: str,
    as_of: datetime,
    market_context: dict[str, object],
    settings: ResearchSettings,
) -> object:
    """Invoke the official TradingAgents client with DeepSeek structured output.

    TradingAgents v0.3.1 routes ``provider='deepseek'`` through its native
    DeepSeek client subclass. The endpoint is supplied by policy and defaults
    to the official endpoint; no ``/v1`` suffix is added by Meridian.
    """

    if settings.provider.lower() != "deepseek":
        raise ValueError(f"unsupported research provider: {settings.provider}")
    # Keep the optional vendor import fully lazy so the deterministic base
    # environment remains usable without TradingAgents installed.
    create_llm_client = importlib.import_module(
        "tradingagents.llm_clients"
    ).create_llm_client

    endpoint = settings.endpoint or DEEPSEEK_ENDPOINT
    client = create_llm_client(
        provider="deepseek",
        model=settings.deep_model or settings.model,
        base_url=endpoint,
        timeout=settings.timeout_seconds,
        max_retries=settings.llm_retry_budget,
    )
    llm = client.get_llm()
    structured = llm.with_structured_output(_StructuredResearchResult)
    context = json.dumps(market_context, sort_keys=True, default=str)
    prompt = (
        f"Analyze the US equity {ticker} as of {as_of.isoformat()}.\n"
        "This is research only. Return the requested structured fields and do not "
        "provide shares, target weights, dollar sizing, leverage, order types, "
        "limit prices, stops, or execution instructions. Evidence must identify "
        "a usable public source, an observed_at timestamp with timezone, and an "
        "evidence_type. Never invent an evidence timestamp after the analysis time.\n"
        f"Available point-in-time market context: {context}"
    )
    result = structured.invoke(prompt)
    return {"structured_output": result}


def _official_graph_runner(
    ticker: str,
    as_of: datetime,
    market_context: dict[str, object],
    settings: ResearchSettings,
) -> object:
    """Run the pinned TradingAgents multi-agent graph and return safe metadata.

    The upstream graph writes full state reports as part of its normal API. We
    redirect every persistence path into a temporary project-local directory
    and return only report-presence/rating metadata; the temporary directory is
    removed before this function returns.
    """

    if settings.provider.lower() != "deepseek":
        raise ValueError(f"unsupported research provider: {settings.provider}")
    if not _live_as_of_within_tolerance(as_of, settings.live_as_of_tolerance_seconds):
        raise HistoricalLiveResearchForbidden(
            "requested as_of is outside the configured live research tolerance"
        )
    graph_cls = importlib.import_module(
        "tradingagents.graph.trading_graph"
    ).TradingAgentsGraph
    default_config = importlib.import_module("tradingagents.default_config").DEFAULT_CONFIG
    selected_analysts = ("market", "social", "news", "fundamentals")
    smoke_root = Path.cwd() / "var" / "tradingagents-smoke"
    smoke_root.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=f"{ticker.lower()}-", dir=smoke_root) as temp_dir:
        temp_path = Path(temp_dir)
        config = deepcopy(default_config)
        config.update(
            {
                "project_dir": str(temp_path),
                "results_dir": str(temp_path / "results"),
                "data_cache_dir": str(temp_path / "cache"),
                "memory_log_path": str(temp_path / "memory.md"),
                "llm_provider": "deepseek",
                "deep_think_llm": settings.deep_model or settings.model,
                "quick_think_llm": settings.quick_model or settings.model,
                "backend_url": settings.endpoint or DEEPSEEK_ENDPOINT,
                "max_debate_rounds": settings.debate_rounds,
                "max_risk_discuss_rounds": settings.debate_rounds,
                "llm_max_retries": settings.llm_retry_budget,
                "checkpoint_enabled": False,
            }
        )
        graph_started = time.monotonic()
        graph = graph_cls(selected_analysts=selected_analysts, debug=False, config=config)
        final_state, rating = graph.propagate(ticker, as_of.date().isoformat(), asset_type="stock")
        duration_seconds = Decimal(str(time.monotonic() - graph_started))
        report_keys = (
            "market_report",
            "sentiment_report",
            "news_report",
            "fundamentals_report",
            "investment_plan",
            "trader_investment_plan",
            "final_trade_decision",
        )
        rating_text = str(rating).strip() if rating is not None else None
        if rating_text is not None and rating_text not in {
            "Buy",
            "Overweight",
            "Hold",
            "Underweight",
            "Sell",
        }:
            raise ValueError("TradingAgentsGraph returned an invalid rating")
        return {
            "graph_rating": rating_text,
            "selected_analysts": selected_analysts,
            "reports_present": tuple(key for key in report_keys if final_state.get(key)),
            "point_in_time_status": PointInTimeStatus.LIVE_RESEARCH_OK,
            "warnings": (
                "TradingAgentsGraph reports do not expose Meridian EvidenceItem provenance.",
                "TradingAgentsGraph exposes a rating but no validated numeric conviction.",
                "TradingAgents v0.3.1 graph wall-time limit is observational; safe cancellation is unavailable.",
            ),
            "token_usage": None,
            "estimated_cost": None,
            "duration_seconds": duration_seconds,
        }


class HistoricalLiveResearchForbidden(RuntimeError):
    """Raised when a LIVE graph request is materially historical."""


def _live_as_of_within_tolerance(
    as_of: datetime,
    tolerance_seconds: int,
    *,
    now: datetime | None = None,
) -> bool:
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        return False
    reference = now or datetime.now(UTC)
    if reference.tzinfo is None or reference.utcoffset() is None:
        return False
    age = (reference - as_of).total_seconds()
    return 0 <= age <= tolerance_seconds


class TradingAgentsResearchEngine:
    """Project-owned research boundary for the pinned TradingAgents release."""

    framework = "TradingAgents"

    def __init__(
        self,
        settings: ResearchSettings,
        *,
        runner: Runner | None = None,
        graph_runner: GraphRunner | None = None,
        mode: ResearchMode = ResearchMode.LIVE,
        replay_store: Any | None = None,
    ) -> None:
        self.settings = settings
        self.runner = runner
        self.graph_runner = graph_runner
        self._injected_runner = runner is not None
        self._injected_graph_runner = graph_runner is not None
        self.mode = mode
        self.replay_store = replay_store
        self.framework_version = _installed_version() or PINNED_TRADINGAGENTS_VERSION

    @property
    def model_name(self) -> str:
        return self.settings.deep_model or self.settings.model

    def analyze(
        self, ticker: str, as_of: datetime, market_context: dict[str, object]
    ) -> ResearchOutcome:
        started = datetime.now(UTC)
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        ticker = ticker.upper()
        if self.mode is ResearchMode.REPLAY:
            if self.replay_store is None:
                return self._outcome(
                    ticker,
                    as_of,
                    started,
                    ResearchStatus.UNAVAILABLE,
                    "REPLAY_STORE_MISSING",
                    "Replay store is required in REPLAY mode.",
                )
            try:
                return self.replay_store.load(ticker, as_of)
            except Exception as error:  # noqa: BLE001 - replay must fail closed
                return self._outcome(
                    ticker,
                    as_of,
                    started,
                    ResearchStatus.INVALID_OUTPUT,
                    "REPLAY_FIXTURE_INVALID",
                    type(error).__name__,
                )

        if self.settings.provider.lower() != "deepseek":
            return self._outcome(
                ticker,
                as_of,
                started,
                ResearchStatus.UNAVAILABLE,
                "UNSUPPORTED_PROVIDER",
                "Only the configured native DeepSeek research provider is enabled.",
            )
        if not self.settings.live_enabled:
            return self._outcome(
                ticker,
                as_of,
                started,
                ResearchStatus.UNAVAILABLE,
                "LIVE_RESEARCH_DISABLED",
                "Live research is disabled by policy; use an explicit live command.",
            )
        graph_path = self.runner is None
        if graph_path and not _live_as_of_within_tolerance(
            as_of, self.settings.live_as_of_tolerance_seconds
        ):
            return self._outcome(
                ticker,
                as_of,
                started,
                ResearchStatus.HISTORICAL_LIVE_CALL_FORBIDDEN,
                "HISTORICAL_LIVE_CALL_FORBIDDEN",
                "Live TradingAgentsGraph is restricted to the configured as-of tolerance.",
            )
        if not os.environ.get("DEEPSEEK_API_KEY"):
            return self._outcome(
                ticker,
                as_of,
                started,
                ResearchStatus.UNAVAILABLE,
                "DEEPSEEK_API_KEY_MISSING",
                "DeepSeek credential is unavailable.",
            )
        if (
            not self._injected_runner
            and not self._injected_graph_runner
            and os.environ.get("DEEPSEEK_API_KEY") == "placeholder"
        ):
            return self._outcome(
                ticker,
                as_of,
                started,
                ResearchStatus.UNAVAILABLE,
                "DEEPSEEK_API_KEY_MISSING",
                "A placeholder credential cannot be used for live research.",
            )
        if (
            not self._injected_runner
            and not self._injected_graph_runner
            and importlib.util.find_spec("tradingagents") is None
        ):
            return self._outcome(
                ticker,
                as_of,
                started,
                ResearchStatus.UNAVAILABLE,
                "TRADINGAGENTS_NOT_INSTALLED",
                "TradingAgents optional dependency is not installed.",
            )
        if (
            not self._injected_runner
            and not self._injected_graph_runner
            and self.framework_version != PINNED_TRADINGAGENTS_VERSION
        ):
            return self._outcome(
                ticker,
                as_of,
                started,
                ResearchStatus.UNAVAILABLE,
                "TRADINGAGENTS_VERSION_MISMATCH",
                "Installed TradingAgents version does not match the pinned release.",
            )
        if not self._injected_runner and not self._injected_graph_runner:
            return self._outcome(
                ticker,
                as_of,
                started,
                ResearchStatus.UNAVAILABLE,
                "LEGACY_DEEPSEEK_RUNTIME_DISABLED",
                "The historical DeepSeek TradingAgents runtime is disabled; "
                "canonical research uses Codex CLI.",
            )

        runner = (
            self.runner
            if self.runner is not None
            else self.graph_runner or _official_graph_runner
        )
        retries = 0
        retry_budget = (
            self.settings.graph_max_retries
            if graph_path
            else self.settings.llm_retry_budget
        )
        while True:
            try:
                raw = runner(ticker, as_of, market_context, self.settings)
                if self.runner is None:
                    return self._graph_outcome(ticker, as_of, started, raw, retries)
                signal, metadata = self._normalize_vendor_result(ticker, as_of, raw)
                completed = datetime.now(UTC)
                return ResearchOutcome(
                    ticker=ticker,
                    as_of=as_of,
                    status=ResearchStatus.AVAILABLE,
                    signal=signal,
                    provider="deepseek",
                    framework=(
                        "TradingAgentsLLMProbe" if self._injected_runner else self.framework
                    ),
                    framework_version=self.framework_version,
                    model_provider="deepseek",
                    model_name=self.model_name,
                    started_at=started,
                    completed_at=completed,
                    mode=self.mode,
                    point_in_time_status=metadata["point_in_time_status"],
                    warnings=metadata["warnings"]
                    + (
                        ("TEST_INJECTED_CLIENT_RUNNER",)
                        if self._injected_runner
                        else ()
                    ),
                    retry_count=retries,
                    token_usage=metadata["token_usage"],
                    estimated_cost=metadata["estimated_cost"],
                    duration_seconds=metadata.get("duration_seconds"),
                )
            except Exception as error:  # noqa: BLE001 - map every provider failure
                code = _classify_error(error)
                if code in {"TIMEOUT", "RATE_LIMIT"} and retries < retry_budget:
                    retries += 1
                    continue
                status = (
                    ResearchStatus.TIMEOUT
                    if code == "TIMEOUT"
                    else ResearchStatus.HISTORICAL_LIVE_CALL_FORBIDDEN
                    if code == "HISTORICAL_LIVE_CALL_FORBIDDEN"
                    else ResearchStatus.REJECTED_EVIDENCE
                    if code == "REJECTED_EVIDENCE"
                    else ResearchStatus.INVALID_OUTPUT
                    if code == "INVALID_OUTPUT"
                    else ResearchStatus.PROVIDER_ERROR
                )
                return self._outcome(
                    ticker,
                    as_of,
                    started,
                    status,
                    code,
                    type(error).__name__,
                    retries,
                )

    def candidate_tickers(
        self,
        tickers: list[str] | tuple[str, ...],
        existing_holdings: list[str] | tuple[str, ...] = (),
    ) -> tuple[str, ...]:
        """Select a bounded, deterministic graph candidate set."""
        budget = self.settings.budget
        if isinstance(budget, dict):
            budget = ResearchBudgetPolicy.model_validate(budget)
        return budget.select_candidates(tickers, existing_holdings)

    def analyze_many(
        self,
        tickers: list[str] | tuple[str, ...],
        as_of: datetime,
        market_contexts: dict[str, dict[str, object]] | None = None,
        existing_holdings: list[str] | tuple[str, ...] = (),
    ) -> tuple[ResearchOutcome, ...]:
        contexts = market_contexts or {}
        ordered = list(self.candidate_tickers(tickers, existing_holdings))
        budget = self.settings.budget
        if isinstance(budget, dict):
            budget = ResearchBudgetPolicy.model_validate(budget)
        workers = min(self.settings.max_parallel_tickers, budget.max_parallel_graphs)
        if workers <= 1:
            return tuple(self.analyze(ticker, as_of, contexts.get(ticker, {})) for ticker in ordered)
        results: dict[str, ResearchOutcome] = {}
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(self.analyze, ticker, as_of, contexts.get(ticker, {})): ticker
                for ticker in ordered
            }
            for future in as_completed(futures):
                ticker = futures[future]
                try:
                    results[ticker] = future.result()
                except Exception as error:  # noqa: BLE001 - isolate one ticker
                    results[ticker] = self._outcome(
                        ticker,
                        as_of,
                        datetime.now(UTC),
                        ResearchStatus.PROVIDER_ERROR,
                        "BATCH_FAILURE",
                        type(error).__name__,
                    )
        return tuple(results[ticker] for ticker in ordered)

    def _normalize_vendor_result(
        self, ticker: str, as_of: datetime, result: object
    ) -> tuple[Any, dict[str, Any]]:
        metadata: dict[str, Any] = {
            "point_in_time_status": PointInTimeStatus.LIVE_RESEARCH_OK,
            "warnings": (),
            "token_usage": None,
            "estimated_cost": None,
            "duration_seconds": None,
        }
        if isinstance(result, dict):
            metadata["warnings"] = tuple(str(item) for item in result.get("warnings", ()))
            point_in_time = result.get("point_in_time_status")
            if point_in_time is not None:
                metadata["point_in_time_status"] = PointInTimeStatus(str(point_in_time))
            usage = result.get("token_usage")
            if isinstance(usage, int):
                metadata["token_usage"] = usage
            elif isinstance(usage, dict) and isinstance(usage.get("total_tokens"), int):
                metadata["token_usage"] = usage["total_tokens"]
            if result.get("estimated_cost") is not None:
                metadata["estimated_cost"] = Decimal(str(result["estimated_cost"]))
            if result.get("duration_seconds") is not None:
                metadata["duration_seconds"] = Decimal(str(result["duration_seconds"]))
            result = result.get("structured_output", result.get("result", result))
        model_dump = getattr(result, "model_dump", None)
        if callable(model_dump):
            result = model_dump(mode="python")
        elif hasattr(result, "__dict__") and not isinstance(result, dict):
            result = vars(result)
        if not isinstance(result, dict):
            raise ValueError("structured TradingAgents result is required")
        allowed = {
            key: value
            for key, value in result.items()
            if key
            in {
                "direction",
                "conviction",
                "fundamental_score",
                "technical_score",
                "sentiment_score",
                "news_score",
                "risk_score",
                "thesis",
                "risks",
                "evidence",
            }
        }
        signal = normalize_signal(
            ticker=ticker,
            as_of=as_of,
            raw=allowed,
            source="TradingAgents:deepseek",
        )
        if not self._injected_runner and any(
            item.source.lower().startswith(("fixture", "synthetic")) for item in signal.evidence
        ):
            raise ValueError("evidence provenance is not acceptable for live research")
        return signal, metadata

    def _graph_outcome(
        self,
        ticker: str,
        as_of: datetime,
        started: datetime,
        result: object,
        retry_count: int,
    ) -> ResearchOutcome:
        """Normalize only safe metadata returned by TradingAgentsGraph.

        TradingAgents v0.3.1 returns rendered report prose plus a five-tier
        rating. The typed PortfolioDecision is consumed inside the upstream
        graph and is not exposed from ``propagate``. Since no numeric
        conviction or source/timestamp evidence crosses that boundary, this
        result is deliberately non-executable and carries no AgentSignal.
        """

        if not isinstance(result, dict):
            raise ValueError("TradingAgentsGraph result metadata is required")
        rating = result.get("graph_rating")
        if not isinstance(rating, str) or rating not in {
            "Buy",
            "Overweight",
            "Hold",
            "Underweight",
            "Sell",
        }:
            raise ValueError("TradingAgentsGraph rating is unavailable or invalid")
        selected = result.get("selected_analysts", ())
        reports = result.get("reports_present", ())
        if not isinstance(selected, (list, tuple)) or not isinstance(reports, (list, tuple)):
            raise ValueError("TradingAgentsGraph metadata lists are invalid")
        point_in_time = result.get(
            "point_in_time_status", PointInTimeStatus.LIVE_RESEARCH_OK
        )
        point_in_time_status = (
            point_in_time
            if isinstance(point_in_time, PointInTimeStatus)
            else PointInTimeStatus(str(point_in_time))
        )
        warnings = result.get("warnings", ())
        if not isinstance(warnings, (list, tuple)):
            warnings = (str(warnings),)
        completed = datetime.now(UTC)
        duration = result.get("duration_seconds")
        if duration is None:
            duration = Decimal(str((completed - started).total_seconds()))
        summary = GraphResearchSummary(
            ticker=ticker,
            as_of=as_of,
            status=ResearchStatus.GRAPH_SUMMARY_ONLY,
            graph_rating=rating,
            selected_analysts=tuple(str(item) for item in selected),
            reports_present=tuple(str(item) for item in reports),
            provider="deepseek",
            model=self.model_name,
            framework_version=self.framework_version,
            started_at=started,
            completed_at=completed,
            warnings=tuple(str(item) for item in warnings),
            point_in_time_status=point_in_time_status,
            token_usage=(
                result.get("token_usage")
                if isinstance(result.get("token_usage"), int)
                else None
            ),
            estimated_cost=(
                Decimal(str(result["estimated_cost"]))
                if result.get("estimated_cost") is not None
                else None
            ),
            duration_seconds=duration,
        )
        return ResearchOutcome(
            ticker=ticker,
            as_of=as_of,
            status=ResearchStatus.GRAPH_SUMMARY_ONLY,
            signal=None,
            provider="deepseek",
            framework="TradingAgentsGraph",
            framework_version=self.framework_version,
            model_provider="deepseek",
            model_name=self.model_name,
            started_at=started,
            completed_at=completed,
            mode=self.mode,
            point_in_time_status=point_in_time_status,
            warnings=tuple(str(item) for item in warnings),
            error_code=None,
            retry_count=retry_count,
            token_usage=(
                result.get("token_usage")
                if isinstance(result.get("token_usage"), int)
                else None
            ),
            estimated_cost=(
                Decimal(str(result["estimated_cost"]))
                if result.get("estimated_cost") is not None
                else None
            ),
            graph_rating=rating,
            selected_analysts=tuple(str(item) for item in selected),
            reports_present=tuple(str(item) for item in reports),
            graph_summary=summary,
            duration_seconds=duration,
        )

    def _outcome(
        self,
        ticker: str,
        as_of: datetime,
        started: datetime,
        status: ResearchStatus,
        error_code: str,
        message: str,
        retry_count: int = 0,
    ) -> ResearchOutcome:
        return ResearchOutcome(
            ticker=ticker,
            as_of=as_of,
            status=status,
            signal=None,
            provider="deepseek",
            framework=self.framework,
            framework_version=self.framework_version,
            model_provider="deepseek",
            model_name=self.model_name,
            started_at=started,
            completed_at=datetime.now(UTC),
            mode=self.mode,
            point_in_time_status=(
                PointInTimeStatus.HISTORICAL_REPLAY_UNSAFE
                if self.mode is ResearchMode.REPLAY
                else PointInTimeStatus.HISTORICAL_LIVE_CALL_FORBIDDEN
                if error_code == "HISTORICAL_LIVE_CALL_FORBIDDEN"
                else PointInTimeStatus.LIVE_RESEARCH_OK
            ),
            warnings=(message,),
            error_code=error_code,
            retry_count=retry_count,
        )


def _classify_error(error: Exception) -> str:
    text = f"{type(error).__name__} {error}".lower()
    if isinstance(error, HistoricalLiveResearchForbidden) or "historical_live_call_forbidden" in text:
        return "HISTORICAL_LIVE_CALL_FORBIDDEN"
    if isinstance(error, TimeoutError) or "timeout" in text or "timed out" in text:
        return "TIMEOUT"
    if "401" in text or "403" in text or "authentication" in text or "api key" in text:
        return "AUTHENTICATION_FAILURE"
    if "quota" in text or "insufficient" in text or "balance" in text:
        return "INSUFFICIENT_QUOTA"
    if "429" in text or "rate limit" in text or "ratelimit" in text:
        return "RATE_LIMIT"
    if "unsupported model" in text or "model not found" in text:
        return "MODEL_UNAVAILABLE"
    if "tool_choice" in text or "tool call" in text:
        return "TOOL_CALL_INCOMPATIBLE"
    if "reasoning_content" in text or "reasoning" in text and "400" in text:
        return "REASONING_INCOMPATIBILITY"
    if "evidence" in text or "timezone" in text or "provenance" in text:
        return "REJECTED_EVIDENCE"
    if isinstance(error, ValueError):
        return "INVALID_OUTPUT"
    return "PROVIDER_ERROR"
