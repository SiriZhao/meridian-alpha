"""Intentionally small, local-only command line interface."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from meridian.adapters.tradingagents import ResearchReplayStore, TradingAgentsResearchEngine
from meridian.audit import AuditStore
from meridian.candidates import CandidateSelector
from meridian.config import load_policies
from meridian.evidence import (
    EvidencePacketBuilder,
    FakeFundamentalEvidenceProvider,
    FakeMacroEvidenceProvider,
    FakeMarketEvidenceProvider,
    FakeNewsEvidenceProvider,
)
from meridian.execution_quote_providers import provider_preflight
from meridian.host_account import (
    HostAccountSnapshotEnvelope,
    normalize_host_snapshot,
)
from meridian.host_readiness import build_host_smoke_report, write_host_smoke_report
from meridian.identity_certification import load_verified_security_certificates
from meridian.market import FakeMarketDataProvider
from meridian.orchestrator import DailyAnalysisService, DailyOrchestrator
from meridian.pipeline import (
    FakeGraphResearchProvider,
    ResearchPipelineMode,
    ResearchPipelineService,
)
from meridian.reporting import report_markdown, research_report_markdown
from meridian.research import (
    FakeGroundedResearchNormalizer,
    FakeResearchEngine,
    GroundedResearchReplayStore,
    GroundedResearchSignal,
    GroundedResearchStatus,
    ResearchMode,
)
from meridian.schemas import (
    AccountSnapshot,
    AgentSignal,
    EvidenceItem,
    FreshnessState,
    MarketSnapshot,
)
from meridian.security_master import DEFAULT_SECURITY_MASTER


def _fixture_market(as_of: datetime) -> FakeMarketDataProvider:
    quotes = {}
    for ticker, last in {"AAPL": "200", "MSFT": "300", "NVDA": "400", "SPY": "600"}.items():
        price = Decimal(last)
        quotes[ticker] = MarketSnapshot(
            ticker=ticker,
            timestamp=as_of,
            last=price,
            bid=price - 1,
            ask=price + 1,
            previous_close=price - 2,
            volume=1_000_000,
            atr14=Decimal("5"),
            vwap=price,
            daily_return=Decimal("0.01"),
            gap_percent=Decimal("0.005"),
            freshness_state=FreshnessState.VERIFIED,
        )
    return FakeMarketDataProvider(quotes)


def _fixture_signal(ticker: str, as_of: datetime) -> AgentSignal:
    return AgentSignal(
        ticker=ticker,
        as_of=as_of,
        direction="BULLISH",
        conviction=Decimal("0.75"),
        fundamental_score=Decimal("0.5"),
        technical_score=Decimal("0.4"),
        sentiment_score=Decimal("0.2"),
        news_score=Decimal("0.1"),
        risk_score=Decimal("0.1"),
        thesis="Synthetic mocked research example; not live investment research.",
        risks=("Synthetic fixture only.",),
        evidence=(
            EvidenceItem(
                source="synthetic-fixture",
                observed_at=as_of,
                evidence_type="fixture",
                summary="Synthetic mocked research evidence",
            ),
        ),
        source="fake-research",
    )


def _parse_date(value: str) -> datetime:
    as_of = datetime.fromisoformat(value)
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise SystemExit("date must be timezone-aware")
    return as_of


def _offline_research_pipeline(as_of: datetime, tickers: tuple[str, ...]):
    providers = (
        FakeMarketEvidenceProvider(),
        FakeFundamentalEvidenceProvider(),
        FakeNewsEvidenceProvider(),
        FakeMacroEvidenceProvider(),
    )
    builder = EvidencePacketBuilder(clock=lambda: as_of)
    grounded: dict[str, GroundedResearchSignal] = {}
    for ticker in tickers:
        evidence = builder.gather(ticker, as_of, providers)
        if evidence.items:
            grounded[ticker] = GroundedResearchSignal(
                ticker=ticker,
                as_of=as_of,
                direction="BULLISH",
                conviction=Decimal("0.6"),
                thesis="Explicit synthetic grounding fixture; not live research.",
                risks=("Synthetic fixture only.",),
                cited_evidence_ids=(evidence.items[0].stable_id,),
                status=GroundedResearchStatus.AVAILABLE,
            )
    features = {
        ticker: {
            "feature_timestamp": as_of,
            "momentum": Decimal("0.2") + Decimal(index) / Decimal("100"),
            "trend": Decimal("0.1"),
        }
        for index, ticker in enumerate(tickers)
    }
    return ResearchPipelineService(
        load_policies(Path.cwd() / "policies").models.research.budget,  # type: ignore[union-attr]
        graph_provider=FakeGraphResearchProvider(),
        evidence_builder=builder,
        evidence_providers=providers,
        normalizer=FakeGroundedResearchNormalizer(grounded),
    ).run(tickers, as_of, features, mode=ResearchPipelineMode.TEST)


def _load_local_env(root: Path) -> None:
    """Load the git-ignored local environment without printing its values."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(root / ".env.local", override=False)


def main() -> None:
    parser = argparse.ArgumentParser(prog="meridian")
    subparsers = parser.add_subparsers(dest="command", required=True)
    config_parser = subparsers.add_parser("config")
    config_parser.add_subparsers(dest="config_command", required=True).add_parser("validate")
    runs_parser = subparsers.add_parser("runs")
    runs_subparsers = runs_parser.add_subparsers(dest="runs_command", required=True)
    runs_subparsers.add_parser("list")
    show = runs_subparsers.add_parser("show")
    show.add_argument("run_id")
    host_smoke = subparsers.add_parser("host-smoke")
    host_smoke.add_argument(
        "snapshot", help="Path to a sanitized HostAccountSnapshotEnvelope JSON file"
    )
    quote_preflight = subparsers.add_parser(
        "quote-preflight",
        help="Show sanitized read-only Alpaca/Polygon quote configuration diagnostics",
    )
    quote_preflight.add_argument(
        "--probe",
        action="store_true",
        help="Perform bounded read-only probes when local provider credentials exist",
    )
    daily = subparsers.add_parser("daily")
    daily.add_argument("--account-fixture", required=True)
    daily.add_argument("--date", required=True)
    daily.add_argument("--profile", choices=("TEST", "REPLAY", "SHADOW_LIVE", "MANUAL_DECISION_SUPPORT"), default="TEST")
    research = subparsers.add_parser("research")
    research.add_argument("ticker")
    research.add_argument("--date", required=True, help="Timezone-aware ISO analysis timestamp")
    research_group = research.add_mutually_exclusive_group()
    research_group.add_argument(
        "--live",
        action="store_true",
        help="Run the full TradingAgentsGraph; may call the configured DeepSeek provider.",
    )
    research_group.add_argument(
        "--replay",
        help="Load a sanitized normalized outcome; never calls a live provider.",
    )
    ranking = subparsers.add_parser("rank")
    ranking.add_argument("--universe", required=True)
    allocation = subparsers.add_parser("allocate")
    allocation.add_argument("--fixture", required=True)
    candidates = subparsers.add_parser("candidates")
    candidates.add_argument("--fixture", required=True)
    evidence = subparsers.add_parser("evidence")
    evidence_subparsers = evidence.add_subparsers(dest="evidence_command", required=True)
    evidence_build = evidence_subparsers.add_parser("build")
    evidence_build.add_argument("ticker")
    evidence_build.add_argument("--fixture", required=True)
    research_ground = subparsers.add_parser("research-ground")
    research_ground.add_argument("ticker")
    research_ground.add_argument("--replay", required=True)
    research_pipeline = subparsers.add_parser("research-pipeline")
    research_pipeline.add_argument("--fixture", required=True)
    research_pipeline.add_argument(
        "--date",
        default="2026-08-28T14:30:00+00:00",
        help="Timezone-aware ISO analysis timestamp",
    )
    args = parser.parse_args()
    root = Path.cwd()
    policies = load_policies(root / "policies")
    if args.command == "quote-preflight":
        _load_local_env(root)
        results = provider_preflight(probe=args.probe)
        print(json.dumps({"providers": [item.model_dump(mode="json") for item in results]}, sort_keys=True))
        return
    if args.command == "host-smoke":
        try:
            security_path = root / "reports" / "gate4f-security-master.json"
            security_master = (
                load_verified_security_certificates(security_path)
                if security_path.exists()
                else DEFAULT_SECURITY_MASTER
            )
            envelope = HostAccountSnapshotEnvelope.model_validate_json(
                Path(args.snapshot).read_text(encoding="utf-8")
            )
            snapshot = normalize_host_snapshot(envelope, security_master=security_master)
            decision = DailyAnalysisService(None, policies).run(
                snapshot, datetime.now(snapshot.as_of.tzinfo)
            )
            readiness = build_host_smoke_report(
                envelope,
                security_master=security_master,
                security_ready=security_master.authoritative_count() == 11,
            )
            report_json = root / "reports" / "gate4f-host-smoke.json"
            report_markdown_path = root / "reports" / "gate4f-host-smoke.md"
            write_host_smoke_report(readiness, report_json, report_markdown_path)
            output = {
                "validation": "VALID",
                "gates": [gate.model_dump(mode="json") for gate in readiness.gates],
                "status": readiness.status,
                "report_json": str(report_json),
                "report_markdown": str(report_markdown_path),
                "blockers": [gate.reason for gate in readiness.gates if gate.status.value == "FAIL"],
                "decision": decision.model_dump(mode="json"),
            }
            print(json.dumps(output, default=str))
        except (OSError, ValueError) as error:
            raise SystemExit(f"HOST_SMOKE_REJECTED:{error}") from error
        return
    if args.command == "config":
        print("Configuration is valid.")
        return
    if args.command == "candidates":
        as_of = datetime.fromisoformat("2026-08-28T14:30:00+00:00")
        tickers = tuple(policies.universe.tickers)
        features = {
            ticker: {
                "feature_timestamp": as_of,
                "momentum": Decimal("0.2") + Decimal(index) / Decimal("100"),
                "trend": Decimal("0.1"),
            }
            for index, ticker in enumerate(tickers)
        }
        selected = CandidateSelector().build(
            tickers,
            features,
            as_of,
            policy=policies.models.research.budget,  # type: ignore[union-attr]
        )
        print(selected.stable_json())
        return
    if args.command == "evidence":
        if args.evidence_command == "build":
            as_of = datetime.fromisoformat("2026-08-28T14:30:00+00:00")
            packet = EvidencePacketBuilder(clock=lambda: as_of).gather(
                args.ticker.upper(),
                as_of,
                (
                    FakeMarketEvidenceProvider(),
                    FakeFundamentalEvidenceProvider(),
                    FakeNewsEvidenceProvider(),
                    FakeMacroEvidenceProvider(),
                ),
            )
            print(packet.stable_json())
            return
    if args.command == "research-ground":
        settings = policies.models.research
        if settings is None:
            raise SystemExit("research settings are not configured")
        as_of = datetime.fromisoformat("2026-08-28T14:30:00+00:00")
        store = GroundedResearchReplayStore(Path(args.replay))
        try:
            summary = store.load_graph(args.ticker.upper(), as_of)
            packet = store.load_packet(args.ticker.upper(), as_of)
            signal = store.load_signal(args.ticker.upper(), as_of)
            print(
                json.dumps(
                    {
                        "graph_summary": summary.model_dump(mode="json"),
                        "evidence_packet": packet.model_dump(mode="json"),
                        "grounded_signal": signal.model_dump(mode="json"),
                        "mode": "REPLAY",
                    },
                    sort_keys=True,
                    indent=2,
                )
            )
        except (FileNotFoundError, ValueError) as error:
            raise SystemExit(f"REPLAY_FIXTURE_INVALID: {error}") from error
        return
    if args.command == "research-pipeline":
        result = _offline_research_pipeline(
            _parse_date(args.date),
            tuple(policies.universe.tickers),
        )
        print(research_report_markdown(result))
        return
    store = AuditStore(root / "var" / "meridian.db")
    if args.command == "runs":
        if args.runs_command == "list":
            print(json.dumps([run.__dict__ for run in store.list_runs()], indent=2))
        else:
            result = store.get_decision_summary(args.run_id)
            if result is None:
                raise SystemExit(f"Unknown run_id: {args.run_id}")
            print(json.dumps(result, indent=2))
        return
    if args.command == "research":
        as_of = datetime.fromisoformat(args.date)
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            from datetime import UTC

            as_of = as_of.replace(tzinfo=UTC)
        settings = policies.models.research
        if settings is None:
            raise SystemExit("research settings are not configured")
        if args.live:
            _load_local_env(root)
            settings = settings.model_copy(update={"live_enabled": True})
            outcome = TradingAgentsResearchEngine(settings, mode=ResearchMode.LIVE).analyze(
                args.ticker.upper(), as_of, {}
            )
            print(outcome.stable_json())
        elif args.replay:
            outcome = TradingAgentsResearchEngine(
                settings,
                mode=ResearchMode.REPLAY,
                replay_store=ResearchReplayStore(Path(args.replay)),
            ).analyze(args.ticker.upper(), as_of, {})
            print(outcome.stable_json())
        else:
            print(_fixture_signal(args.ticker.upper(), as_of).stable_json())
        return
    if args.command == "rank":
        print(
            json.dumps(
                {"status": "RESEARCH NOT GROUNDED", "reason": "rank requires certified research"}
            )
        )
        return
    if args.command == "allocate":
        print(
            json.dumps(
                {
                    "status": "RESEARCH NOT GROUNDED",
                    "reason": "allocate requires certified research",
                }
            )
        )
        return
    as_of = datetime.fromisoformat(args.date)
    snapshot = AccountSnapshot.model_validate_json(
        (root / args.account_fixture).read_text(encoding="utf-8")
    )
    signals = {ticker: _fixture_signal(ticker, as_of) for ticker in policies.universe.tickers}
    decision = DailyAnalysisService(
        DailyOrchestrator(policies, _fixture_market(as_of), FakeResearchEngine(signals), store)
    ).run(snapshot, as_of)
    print(report_markdown(decision, profile=args.profile))
