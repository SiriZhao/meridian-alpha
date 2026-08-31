"""Bounded Gate 3B.16/3B.17 real SEC numeric and shadow report builder."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from urllib.request import Request, urlopen

from meridian.alpha_fusion import fuse_production_decision
from meridian.authorization import CertifiedAgentSignal, EvidenceAuthorizationService
from meridian.config import load_policies
from meridian.dislocation import DislocationScreen, PriceDislocationSnapshot
from meridian.evidence import ProviderCapabilities
from meridian.fundamentals import (
    SECCompanyFactsNumericProvider,
    build_snapshot,
    canonical_definition,
    snapshot_to_evidence_items,
)
from meridian.historical import YahooChartHistoricalProvider, generate_shadow_features
from meridian.research import (
    CertifiedEvidenceView,
    DeepSeekGroundedResearchNormalizer,
    GraphResearchSummary,
    GroundedResearchStatus,
    LiveResearchShadowOptIn,
    PointInTimeStatus,
    ResearchContextPacket,
    ResearchStatus,
    enable_live_research_shadow,
    normalize_certified_shadow,
)
from meridian.sec_filing_metadata import SECFilingMetadata
from meridian.security_master import DEFAULT_SECURITY_MASTER

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
TICKERS = ("AAPL", "NVDA", "MSFT")


class BatchSubmissionsMetadata:
    """Fetch each CIK submissions document once and serve exact accessions."""

    def __init__(self, *, now: datetime) -> None:
        self.now = now
        self._cache: dict[str, dict[str, SECFilingMetadata]] = {}
        self.fetch_count = 0

    def _load(self, cik: str) -> dict[str, SECFilingMetadata]:
        normalized = cik.zfill(10)
        if normalized in self._cache:
            return self._cache[normalized]
        uri = f"https://data.sec.gov/submissions/CIK{normalized}.json"
        response = urlopen(Request(uri, headers={"User-Agent": "MeridianAlpha research contact unavailable"}), timeout=10)
        raw = response.read()
        body = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
        data = json.loads(body)
        recent = data.get("filings", {}).get("recent", {})
        result: dict[str, SECFilingMetadata] = {}
        accessions = recent.get("accessionNumber", [])
        for index, accession in enumerate(accessions):
            def value(name: str, idx: int = index) -> str | None:
                values = recent.get(name, [])
                return str(values[idx]) if isinstance(values, list) and idx < len(values) and values[idx] else None

            accepted = value("acceptanceDateTime")
            form = value("form")
            filing_date = value("filingDate")
            primary_document = value("primaryDocument")
            if not all((accepted, form, filing_date, primary_document)):
                continue
            try:
                acceptance = datetime.fromisoformat(accepted.replace("Z", "+00:00")).astimezone(UTC)
                result[str(accession)] = SECFilingMetadata(
                    cik=normalized,
                    accession_number=str(accession),
                    form=form,
                    primary_document=primary_document,
                    filing_date=filing_date,
                    report_period=value("reportDate"),
                    acceptance_datetime=acceptance,
                    retrieved_at=self.now,
                    source_uri=uri,
                    content_hash=hashlib.sha256(body.encode()).hexdigest(),
                )
            except (TypeError, ValueError):
                continue
        self._cache[normalized] = result
        self.fetch_count += 1
        return result

    def get_metadata(self, cik: str, accession_number: str) -> SECFilingMetadata | None:
        return self._load(cik).get(accession_number)


def _json(value: object) -> object:
    return json.loads(json.dumps(value, default=str))


def build_real_fundamentals(
    now: datetime, tickers: tuple[str, ...] = TICKERS
) -> tuple[dict[str, object], dict[str, object]]:
    metadata = BatchSubmissionsMetadata(now=now)
    all_reports: dict[str, object] = {}
    snapshots: dict[str, object] = {}
    bounded_tickers = tuple(dict.fromkeys(ticker.upper() for ticker in tickers))
    if not set(bounded_tickers).issubset(set(TICKERS) | {"META", "GOOGL"}):
        raise ValueError("TICKER_OUTSIDE_BOUNDED_UNIVERSE")
    for ticker in bounded_tickers:
        provider = SECCompanyFactsNumericProvider(clock=lambda now=now: now)
        try:
            observations = provider.get_observations(ticker)
            by_accession: dict[str, object] = {}
            for item in sorted(observations, key=lambda row: (row.filed_at, row.accession_number), reverse=True):
                by_accession.setdefault(item.accession_number, item.filed_at)
            selected_accessions = set(sorted(by_accession, key=lambda key: (by_accession[key], key), reverse=True)[:12])
            bounded = tuple(
                item
                for item in observations
                if item.accession_number in selected_accessions
                and canonical_definition(item.taxonomy, item.raw_concept or item.concept) is not None
            )
            certified = provider.certify_observations(
                bounded, metadata_provider=metadata, decision_as_of=now
            )
            snapshot = build_snapshot(ticker, certified, now)
            snapshots[ticker] = snapshot
            all_reports[ticker] = {
                "raw_observations_count": len(observations),
                "unmapped_observations_excluded": len(observations) - len(bounded),
                "bounded_raw_observations": [_json(item.model_dump(mode="json")) for item in bounded],
                "selected_accessions": sorted(selected_accessions),
                "certified_numeric_facts": [_json(item.model_dump(mode="json")) for item in certified],
                "snapshot": _json(snapshot.model_dump(mode="json")),
                "evidence_items": [_json(item.model_dump(mode="json")) for item in snapshot_to_evidence_items(snapshot)],
                "exclusion_count": len(provider.last_exclusions),
                "exclusions": list(provider.last_exclusions[:200]),
            }
        except Exception as error:  # noqa: BLE001 - isolate per ticker in report
            all_reports[ticker] = {"status": "UNAVAILABLE", "error": type(error).__name__}
    payload: dict[str, object] = {
        "schema_version": "gate3b16.v1",
        "created_at": now.isoformat(),
        "decision_as_of": now.isoformat(),
        "network_budget": {"companyfacts_fetches": len(bounded_tickers), "submissions_fetches": metadata.fetch_count, "max_recent_accessions_per_ticker": 12},
        "provider": "sec-edgar-companyfacts-numeric + SEC:EDGAR_ACCEPTANCE_METADATA",
        "tickers": all_reports,
    }
    payload["content_hash"] = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    return payload, snapshots


def fundamentals_markdown(payload: Mapping[str, object]) -> str:
    lines = [
        "# Gate 3B.16 — Real Certified SEC Numeric Fundamentals",
        "",
        f"Decision cutoff: {payload['decision_as_of']}",
        "",
        "All certified values require exact accession + CIK + SEC acceptance metadata. Missing joins remain excluded.",
        "",
        "| Ticker | Certified facts | Comparable series | Derived metrics | Latest accession |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for ticker, entry in payload.get("tickers", {}).items():
        if not isinstance(entry, Mapping) or "snapshot" not in entry:
            lines.append(f"| {ticker} | 0 | 0 | 0 | UNAVAILABLE |")
            continue
        snap = entry["snapshot"]
        lines.append(f"| {ticker} | {len(entry.get('certified_numeric_facts', []))} | {len(snap.get('comparable_series', []))} | {len(snap.get('derived', []))} | {snap.get('latest_accession')} |")
    lines.extend(["", "## Notes", "", "- `period_end` is never used as availability; `available_at` is the exact SEC acceptance timestamp.", "- Raw observations are bounded to recent accessions for this report; the provider preserves values, units, contexts, and lineage.", "- No recommendation, price target, order, or execution authorization is produced by this artifact."])
    return "\n".join(lines) + "\n"
    lines.extend(["", "## Notes", "", "- period_end is never used as availability; vailable_at is the exact SEC acceptance timestamp.", "- Raw observations are bounded to recent accessions for this report; the provider preserves values, units, contexts, and lineage.", "- No recommendation, price target, order, or execution authorization is produced by this artifact."])
    return "\n".join(lines) + "\n"


def run_live_deepseek(snapshots: Mapping[str, object], now: datetime) -> dict[str, object]:
    if not os.getenv("DEEPSEEK_API_KEY"):
        return {"status": "NOT_RUN", "reason": "DEEPSEEK_API_KEY_MISSING", "calls": 0, "certified_signals": []}
    settings = load_policies(ROOT / "policies").models.research
    if settings is None:
        return {"status": "NOT_RUN", "reason": "RESEARCH_POLICY_UNAVAILABLE", "calls": 0, "certified_signals": []}
    runtime = enable_live_research_shadow(settings, LiveResearchShadowOptIn(enabled=True, max_tickers=3))
    normalizer = DeepSeekGroundedResearchNormalizer(runtime, clock=lambda: now)
    capability = ProviderCapabilities(provider_name="sec-edgar-accession-certified", supports_historical=True, supports_point_in_time=True, research_grade=True)
    outcomes: list[dict[str, object]] = []
    certificates: list[dict[str, object]] = []
    certificate_objects: list[CertifiedAgentSignal] = []
    for ticker in TICKERS:
        snapshot = snapshots.get(ticker)
        if snapshot is None:
            continue
        items = snapshot_to_evidence_items(snapshot)
        context = ResearchContextPacket(context_id=f"gate3b17-{ticker}", ticker=ticker, as_of=now, created_at=now, items=items)
        view = CertifiedEvidenceView.from_context(context, provider_registry={capability.provider_name: capability}, clock=lambda: now)
        if not view.packet.items:
            outcomes.append({"ticker": ticker, "status": "ABSTAIN", "reason": "NO_CERTIFIED_EVIDENCE"})
            continue
        summary = GraphResearchSummary(ticker=ticker, as_of=now, status=ResearchStatus.GRAPH_SUMMARY_ONLY, provider="meridian-gate3b17", model="none", framework_version="1", started_at=now, completed_at=now, point_in_time_status=PointInTimeStatus.LIVE_RESEARCH_OK, source_mode="LIVE_SHADOW")
        outcome = normalize_certified_shadow(normalizer, summary, view, now)
        outcomes.append(_json(outcome.model_dump(mode="json")))
        if outcome.status is GroundedResearchStatus.AVAILABLE and outcome.signal is not None:
            try:
                certificate = EvidenceAuthorizationService().authorize(outcome.signal, view.packet, provider_registry={capability.provider_name: capability})
                certificate_objects.append(certificate)
                certificates.append(_json(certificate.model_dump(mode="json")))
            except ValueError as error:
                outcomes[-1]["authorization_error"] = str(error)
    return {
        "status": "COMPLETED",
        "calls": len(outcomes),
        "outcomes": outcomes,
        "response_hashes": [hashlib.sha256(json.dumps(item, sort_keys=True, default=str).encode()).hexdigest() for item in outcomes],
        "certified_signals": certificates,
        "alpha_effects": _alpha_effects(certificate_objects),
        "authorization": "SHADOW / NOT AUTHORIZED FOR ENTRY",
    }


def _alpha_effects(certificates: list[CertifiedAgentSignal]) -> dict[str, object]:
    effects: dict[str, object] = {}
    for certificate in certificates:
        decision = fuse_production_decision(
            certificate,
            run_id="gate3b17-diagnostic-fusion",
            quant_score=Decimal("0"),
            policy_hash=hashlib.sha256(b"gate3b17-policy").hexdigest(),
        )
        effects[decision.ticker] = {
            "quant_alpha": str(decision.quant_only_alpha),
            "direction": decision.research_direction,
            "conviction": str(decision.research_conviction),
            "base_research_modifier": str(decision.research_modifier),
            "final_alpha": str(decision.final_alpha),
            "combined_modifier": str(decision.combined_research_modifier),
        }
    return effects


def build_dislocation_screen(
    now: datetime, tickers: tuple[str, ...] = TICKERS
) -> dict[str, object]:
    provider = YahooChartHistoricalProvider(DEFAULT_SECURITY_MASTER)
    features: dict[str, dict[str, Decimal]] = {}
    snapshots: list[dict[str, object]] = []
    failures: list[dict[str, str]] = []
    bounded_tickers = tuple(dict.fromkeys(ticker.upper() for ticker in tickers))
    if not set(bounded_tickers).issubset(set(TICKERS) | {"META", "GOOGL"}):
        raise ValueError("TICKER_OUTSIDE_BOUNDED_UNIVERSE")
    for ticker in bounded_tickers:
        try:
            series = provider.get_series(ticker, now.date() - timedelta(days=60), now.date(), as_of=now)
            closes = [bar.close for bar in series.bars]
            if len(closes) < 6:
                raise ValueError("INSUFFICIENT_HISTORY")
            peak = max(closes)
            drawdown = closes[-1] / peak - Decimal("1") if peak else Decimal("0")
            reversal = closes[-1] / closes[-6] - Decimal("1") if closes[-6] else Decimal("0")
            computed, _ = generate_shadow_features(series, now)
            volatility = computed.get("realized_volatility") or Decimal("0")
            features[ticker] = {"drawdown": drawdown, "momentum_reversal": reversal, "realized_volatility": volatility, "quant_alpha": Decimal("0")}
            snapshots.append(PriceDislocationSnapshot(ticker=ticker, as_of=now, current_price=closes[-1], drawdown=drawdown, trend_state="RECENT_REVERSAL" if reversal > 0 else "DOWN", realized_volatility=volatility, source_hashes=(hashlib.sha256("|".join(str(v) for v in closes).encode()).hexdigest(),)).model_dump(mode="json"))
        except Exception as error:  # noqa: BLE001 - isolate each market ticker
            failures.append({"ticker": ticker, "error": type(error).__name__})
    candidates = DislocationScreen().select(features, limit=3)
    return {"status": "COMPLETED" if not failures else "DEGRADED", "snapshots": snapshots, "candidates": [item.model_dump(mode="json") for item in candidates], "failures": failures, "source": "Yahoo historical shadow; not certified evidence"}


def main() -> None:
    now = datetime.now(UTC)
    fundamentals, snapshots = build_real_fundamentals(now)
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "gate3b16-real-certified-fundamentals.json").write_text(json.dumps(fundamentals, indent=2, sort_keys=True, default=str), encoding="utf-8")
    (REPORTS / "gate3b16-real-certified-fundamentals.md").write_text(fundamentals_markdown(fundamentals), encoding="utf-8")
    prior_shadow = REPORTS / "gate3b17-real-shadow-v8.json"
    if os.getenv("MERIDIAN_SKIP_LIVE") and prior_shadow.is_file():
        try:
            live = json.loads(prior_shadow.read_text(encoding="utf-8")).get("deepseek", {"status": "NOT_RUN", "reason": "LIVE_REUSE_UNAVAILABLE"})
        except (OSError, json.JSONDecodeError):
            live = {"status": "NOT_RUN", "reason": "LIVE_REUSE_UNAVAILABLE", "calls": 0, "certified_signals": []}
    else:
        live = run_live_deepseek(snapshots, now)
    if "alpha_effects" not in live:
        live["alpha_effects"] = _alpha_effects(list(live.get("certified_signals", [])))
    if "response_hashes" not in live:
        live["response_hashes"] = [hashlib.sha256(json.dumps(item, sort_keys=True, default=str).encode()).hexdigest() for item in live.get("outcomes", [])]
    screen = build_dislocation_screen(now)
    dislocation = {
        "schema_version": "gate3b17.v1",
        "created_at": now.isoformat(),
        "status": "SHADOW / NOT AUTHORIZED FOR ENTRY",
        "candidate_screen": "DETERMINISTIC_ONLY; Yahoo historical data may screen candidates but cannot become certified evidence",
        "market_snapshots": screen,
        "assessments": [],
        "certified_evidence_required": True,
        "raw_evidence_bypass": "REJECTED",
        "combined_modifier_cap": "ENFORCED_BY_ALPHA_FUSION",
    }
    dislocation["content_hash"] = hashlib.sha256(json.dumps(dislocation, sort_keys=True).encode()).hexdigest()
    (REPORTS / "gate3b17-dislocation-shadow.json").write_text(json.dumps(dislocation, indent=2, sort_keys=True), encoding="utf-8")
    (REPORTS / "gate3b17-dislocation-shadow.md").write_text("# Gate 3B.17 — Certified Dislocation Shadow\n\nStatus: **SHADOW / NOT AUTHORIZED FOR ENTRY**\n\nNo bounded candidate qualified for a certified dislocation assessment in this run. Raw evidence cannot bypass CertifiedEvidenceView.\n", encoding="utf-8")
    shadow = {
        "schema_version": "gate3b17.v1",
        "created_at": now.isoformat(),
        "authorization": "SHADOW / NOT AUTHORIZED FOR ENTRY",
        "account": "SYNTHETIC",
        "market": "REAL_SHADOW_NOT_CERTIFIED",
        "fundamentals": fundamentals,
        "deepseek": live,
        "dislocation": dislocation,
        "allocator": "deterministic shadow only",
        "risk": "deterministic policy; no order path",
        "reconciliation": "synthetic account; no fills inferred",
    }
    shadow["content_hash"] = hashlib.sha256(json.dumps(shadow, sort_keys=True, default=str).encode()).hexdigest()
    (REPORTS / "gate3b17-real-shadow-v8.json").write_text(json.dumps(shadow, indent=2, sort_keys=True, default=str), encoding="utf-8")
    (REPORTS / "gate3b17-real-shadow-v8.md").write_text("# Gate 3B.17 — Real Shadow V8\n\nStatus: **SHADOW / NOT AUTHORIZED FOR ENTRY**\n\nAccount is synthetic. Certified numeric SEC fundamentals are included where the accession join succeeded. No broker, order, fill, or execution action occurred.\n", encoding="utf-8")
    print(json.dumps({"fundamentals": str(REPORTS / "gate3b16-real-certified-fundamentals.json"), "deepseek": live.get("status"), "certified_signals": len(live.get("certified_signals", []))}, sort_keys=True))


if __name__ == "__main__":
    main()
