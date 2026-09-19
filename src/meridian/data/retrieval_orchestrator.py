"""Bounded cache/provider/validation loop for research evidence acquisition."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from meridian.analytics.derived_market_features import derive_market_features
from meridian.data.models import (
    DataCategory,
    DataQualityScore,
    DataStatus,
    EvidenceRecord,
    ProviderFailure,
    ProviderHealth,
    ProviderResult,
    RequirementStatus,
    ResearchDataRequirement,
    ResearchEvidencePackage,
    SourceConflict,
    SourceType,
    ValidationStatus,
    quality_grade,
)
from meridian.data.providers.base import RetrievalProvider, RetrievalProviderError
from meridian.market import Bar

_NUMERICAL = {
    DataCategory.PRICE_HISTORY,
    DataCategory.VOLUME_HISTORY,
    DataCategory.MARKET_SNAPSHOT,
    DataCategory.VOLATILITY,
    DataCategory.TECHNICAL,
    DataCategory.FUNDAMENTALS,
    DataCategory.VALUATION,
    DataCategory.MACRO,
    DataCategory.RATES,
    DataCategory.BENCHMARK,
}


class EvidenceCache:
    """Requirement-aware JSON cache; cached facts retain their original source."""

    def __init__(self, directory: Path, *, clock: Callable[[], datetime] | None = None) -> None:
        self.directory = directory
        self.clock = clock or (lambda: datetime.now(UTC))

    @staticmethod
    def _digest(requirement: ResearchDataRequirement, as_of: datetime) -> str:
        body = requirement.model_dump_json(exclude={"status"}) + "|" + as_of.isoformat()
        return hashlib.sha256(body.encode()).hexdigest()

    def _path(self, requirement: ResearchDataRequirement, as_of: datetime) -> Path:
        return self.directory / (self._digest(requirement, as_of) + ".json")

    def load(
        self, requirement: ResearchDataRequirement, *, as_of: datetime
    ) -> tuple[EvidenceRecord, ...]:
        path = self._path(requirement, as_of)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            records = tuple(EvidenceRecord.model_validate(item) for item in payload["evidence"])
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            return ()
        now = self.clock()
        if not records or any(
            item.expires_at is None
            or item.expires_at <= now
            or item.timestamp > as_of
            or (item.available_at is not None and item.available_at > as_of)
            or item.as_of != as_of
            or item.requirement_key != requirement.key
            for item in records
        ):
            return ()
        return tuple(
            item.model_copy(update={"source_type": SourceType.LOCAL_CACHE}) for item in records
        )

    def store(
        self,
        requirement: ResearchDataRequirement,
        records: Sequence[EvidenceRecord],
        *,
        as_of: datetime,
    ) -> None:
        if not records:
            return
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self._path(requirement, as_of)
        temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
        payload = {
            "cache_key": self._digest(requirement, as_of),
            "as_of": as_of.isoformat(),
            "source": [item.source for item in records],
            "retrieved_at": max(item.retrieved_at for item in records).isoformat(),
            "expires_at": min(
                item.expires_at for item in records if item.expires_at is not None
            ).isoformat(),
            "evidence": [item.model_dump(mode="json") for item in records],
        }
        try:
            temporary.write_text(
                json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str),
                encoding="utf-8",
            )
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


class DataQualityGate:
    """Score quality while preserving hard blocking requirements."""

    def __init__(self, *, minimum_score: int = 60) -> None:
        self.minimum_score = minimum_score

    def evaluate(
        self,
        requirements: Sequence[ResearchDataRequirement],
        evidence: Sequence[EvidenceRecord],
        conflicts: Sequence[SourceConflict],
        *,
        as_of: datetime,
    ) -> tuple[DataQualityScore, DataStatus]:
        accepted = tuple(
            item for item in evidence if item.validation_status is not ValidationStatus.REJECTED
            and item.timestamp <= as_of and (item.expires_at is None or item.expires_at > as_of)
        )
        keys = {item.requirement_key for item in accepted}
        required = tuple(item for item in requirements if item.required)
        missing = tuple(item.key for item in required if item.key not in keys)
        total_weight = sum((item.importance for item in requirements), Decimal("0"))
        found_weight = sum(
            (item.importance for item in requirements if item.key in keys), Decimal("0")
        )
        completeness = found_weight / total_weight if total_weight else Decimal("1")
        fresh = tuple(
            item
            for item in accepted
            if item.expires_at is None or item.expires_at > as_of
        )
        freshness = Decimal(len(fresh)) / Decimal(len(accepted)) if accepted else Decimal("0")
        source_quality = (
            sum((item.confidence for item in accepted), Decimal("0")) / Decimal(len(accepted))
            if accepted
            else Decimal("0")
        )
        agreement = Decimal("0") if conflicts else Decimal("1")
        timestamp_integrity = (
            Decimal(sum(item.timestamp <= as_of for item in accepted)) / Decimal(len(accepted))
            if accepted
            else Decimal("0")
        )
        required_symbols = {item.symbol for item in required}
        covered_symbols = {item.symbol for item in accepted}
        coverage = (
            Decimal(len(required_symbols & covered_symbols)) / Decimal(len(required_symbols))
            if required_symbols
            else Decimal("1")
        )
        raw_score = (
            completeness * Decimal("45")
            + freshness * Decimal("15")
            + source_quality * Decimal("15")
            + agreement * Decimal("10")
            + timestamp_integrity * Decimal("10")
            + coverage * Decimal("5")
        )
        score = max(0, min(100, int(raw_score.quantize(Decimal("1")))))
        blocking = list(missing)
        if score < self.minimum_score:
            blocking.append("QUALITY_SCORE_BELOW_60")
        if conflicts:
            blocking.extend(item.requirement_key for item in conflicts)
        quality = DataQualityScore(
            score=score,
            grade=quality_grade(score),
            completeness=completeness,
            freshness=freshness,
            source_quality=source_quality,
            cross_source_agreement=agreement,
            timestamp_integrity=timestamp_integrity,
            coverage=coverage,
            blocking_missing=tuple(dict.fromkeys(blocking)),
        )
        if conflicts:
            status = DataStatus.SOURCE_CONFLICT
        elif missing:
            missing_categories = {item.category for item in required if item.key in missing}
            if missing_categories & {
                DataCategory.PRICE_HISTORY,
                DataCategory.VOLUME_HISTORY,
                DataCategory.MARKET_SNAPSHOT,
                DataCategory.VOLATILITY,
                DataCategory.TECHNICAL,
                DataCategory.BENCHMARK,
            }:
                status = DataStatus.NUMERICAL_DATA_MISSING
            elif missing_categories & {DataCategory.FUNDAMENTALS, DataCategory.VALUATION, DataCategory.EARNINGS}:
                status = DataStatus.FUNDAMENTAL_DATA_MISSING
            elif DataCategory.MACRO in missing_categories or DataCategory.RATES in missing_categories:
                status = DataStatus.MACRO_DATA_MISSING
            else:
                status = DataStatus.DATA_RETRIEVAL_FAILED
        elif score < self.minimum_score:
            status = DataStatus.DATA_RETRIEVAL_FAILED
        elif any(item.key not in keys for item in requirements):
            status = DataStatus.DATA_DEGRADED
        else:
            status = DataStatus.DATA_COMPLETE
        return quality, status


def detect_source_conflicts(
    evidence: Sequence[EvidenceRecord], *, price_tolerance: Decimal = Decimal("0.01")
) -> tuple[SourceConflict, ...]:
    grouped: dict[str, list[EvidenceRecord]] = {}
    for item in evidence:
        if item.category in _NUMERICAL:
            grouped.setdefault(item.requirement_key, []).append(item)
    conflicts: list[SourceConflict] = []
    for key, records in grouped.items():
        providers = {item.provider for item in records}
        if len(records) < 2 or len(providers) < 2:
            continue
        values = _comparable_values(records)
        if values is None:
            continue
        baseline = values[0]
        if baseline == 0:
            relative = Decimal("0") if all(value == 0 for value in values) else Decimal("1")
        else:
            relative = max(abs(value - baseline) / abs(baseline) for value in values[1:])
        tolerance = (
            price_tolerance
            if records[0].category
            in {
                DataCategory.MARKET_SNAPSHOT,
                DataCategory.PRICE_HISTORY,
                DataCategory.VOLUME_HISTORY,
                DataCategory.BENCHMARK,
            }
            else Decimal("0.02")
        )
        if relative > tolerance:
            conflicts.append(
                SourceConflict(
                    requirement_key=key,
                    field=records[0].field,
                    symbol=records[0].symbol,
                    evidence_ids=tuple(item.evidence_id or "" for item in records),
                    relative_difference=relative,
                    tolerance=tolerance,
                )
            )
    return tuple(conflicts)


def _comparable_values(records: Sequence[EvidenceRecord]) -> list[Decimal] | None:
    if all(isinstance(item.value, (str, int, float, Decimal)) for item in records):
        try:
            return [Decimal(str(item.value)) for item in records]
        except ArithmeticError:
            return None
    if all(isinstance(item.value, dict) for item in records):
        values: list[Decimal] = []
        for item in records:
            value = item.value.get("price") or item.value.get("last")
            if value is None:
                return None
            try:
                values.append(Decimal(str(value)))
            except ArithmeticError:
                return None
        return values
    if all(isinstance(item.value, list) for item in records):
        closes_by_record: list[dict[str, Decimal]] = []
        for item in records:
            closes: dict[str, Decimal] = {}
            for row in item.value:
                if not isinstance(row, dict):
                    continue
                session = row.get("session") or row.get("observed_at")
                close = row.get("close")
                if session is None or close is None:
                    continue
                try:
                    closes[str(session)[:10]] = Decimal(str(close))
                except ArithmeticError:
                    continue
            if not closes:
                return None
            closes_by_record.append(closes)
        common_sessions = set(closes_by_record[0])
        for closes in closes_by_record[1:]:
            common_sessions.intersection_update(closes)
        if not common_sessions:
            return None
        latest = max(common_sessions)
        return [closes[latest] for closes in closes_by_record]
    return None


class RetrievalOrchestrator:
    """Retrieve every requirement with bounded retries and visible fallback."""

    def __init__(
        self,
        providers: Sequence[RetrievalProvider],
        *,
        cache: EvidenceCache | None = None,
        quality_gate: DataQualityGate | None = None,
        audit_root: Path | None = None,
        max_retries: int = 1,
        circuit_breaker_failures: int = 3,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.providers = tuple(providers)
        self.cache = cache
        self.quality_gate = quality_gate or DataQualityGate()
        self.audit_root = audit_root
        self.max_retries = max_retries
        self.circuit_breaker_failures = circuit_breaker_failures
        self.sleeper = sleeper
        self.clock = clock or (lambda: datetime.now(UTC))
        self._failures: dict[str, int] = {}
        self._last_success: dict[str, datetime] = {}

    def retrieve(
        self,
        requirements: Sequence[ResearchDataRequirement],
        *,
        as_of: datetime,
        existing_evidence: Sequence[EvidenceRecord] = (),
        rounds: int = 1,
        planner_summary: str = "",
    ) -> ResearchEvidencePackage:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("RETRIEVAL_AS_OF_TIMEZONE_REQUIRED")
        ordered = tuple(
            sorted(
                requirements,
                key=lambda item: (
                    0 if item.category in {DataCategory.PRICE_HISTORY, DataCategory.VOLUME_HISTORY, DataCategory.BENCHMARK} else 1,
                    not item.required,
                    item.key,
                ),
            )
        )
        evidence = list(existing_evidence)
        results: list[ProviderResult] = []
        present = {item.requirement_key for item in evidence}
        for requirement in ordered:
            if requirement.key in present:
                continue
            cached = self.cache.load(requirement, as_of=as_of) if self.cache else ()
            if cached:
                evidence.extend(cached)
                present.add(requirement.key)
                results.append(self._cache_result(requirement, cached))
                continue
            accepted: list[EvidenceRecord] = []
            target_successes = 2 if requirement.category in _NUMERICAL else 1
            for provider in self.providers:
                if not provider.supports(requirement):
                    continue
                if self._failures.get(provider.provider_name, 0) >= self.circuit_breaker_failures:
                    results.append(self._open_circuit(provider.provider_name, requirement))
                    continue
                result = self._attempt(provider, requirement, as_of=as_of)
                results.append(result)
                if result.evidence:
                    with_expiry = tuple(
                        item.model_copy(update={"expires_at": self._expiry(requirement.category, item.retrieved_at)})
                        for item in result.evidence
                    )
                    evidence.extend(with_expiry)
                    accepted.extend(with_expiry)
                    if len({item.provider for item in accepted}) >= target_successes:
                        break
            if accepted:
                present.add(requirement.key)
                if self.cache:
                    try:
                        self.cache.store(requirement, accepted, as_of=as_of)
                    except OSError:
                        pass
        evidence.extend(self._derive(evidence, as_of=as_of))
        unique = {item.evidence_id: item for item in evidence if item.evidence_id}
        evidence_tuple = tuple(unique.values())
        conflicts = detect_source_conflicts(evidence_tuple)
        quality, status = self.quality_gate.evaluate(
            ordered, evidence_tuple, conflicts, as_of=as_of
        )
        available = {item.requirement_key for item in evidence_tuple}
        resolved_requirements = tuple(
            item.model_copy(
                update={
                    "status": RequirementStatus.CONFLICT
                    if any(conflict.requirement_key == item.key for conflict in conflicts)
                    else RequirementStatus.RETRIEVED
                    if item.key in available
                    else RequirementStatus.FAILED
                }
            )
            for item in ordered
        )
        package = ResearchEvidencePackage(
            as_of=as_of,
            created_at=self.clock(),
            status=status,
            requirements=resolved_requirements,
            evidence=evidence_tuple,
            provider_results=tuple(results),
            conflicts=conflicts,
            quality=quality,
            source_count=len({(item.provider, item.source) for item in evidence_tuple}),
            rounds=rounds,
            planner_summary=planner_summary,
            unresolved=quality.blocking_missing,
        )
        self._audit(package)
        return package

    def _attempt(
        self, provider: RetrievalProvider, requirement: ResearchDataRequirement, *, as_of: datetime
    ) -> ProviderResult:
        started = time.monotonic()
        last_error = RetrievalProviderError("PROVIDER_FAILED")
        for attempt in range(1, self.max_retries + 2):
            try:
                records = provider.retrieve(requirement, as_of=as_of)
                if not records or any(
                    item.requirement_key != requirement.key
                    or item.timestamp > as_of
                    or item.as_of != as_of
                    or (item.available_at is not None and item.available_at > as_of)
                    for item in records
                ):
                    raise RetrievalProviderError("PROVIDER_INVALID_RESPONSE")
                self._failures[provider.provider_name] = 0
                self._last_success[provider.provider_name] = self.clock()
                return ProviderResult(
                    provider=provider.provider_name,
                    requirement_key=requirement.key,
                    evidence=records,
                    health=self._health(provider.provider_name),
                    elapsed_ms=round((time.monotonic() - started) * 1000),
                )
            except RetrievalProviderError as error:
                last_error = error
                if not error.retryable or attempt > self.max_retries:
                    break
                self.sleeper(0.1 * (2 ** (attempt - 1)))
            except (OSError, TimeoutError):
                last_error = RetrievalProviderError("PROVIDER_TEMPORARY_FAILURE", retryable=True)
                if attempt > self.max_retries:
                    break
                self.sleeper(0.1 * (2 ** (attempt - 1)))
            except (ValueError, TypeError, KeyError, AttributeError):
                last_error = RetrievalProviderError("PROVIDER_MALFORMED_RESPONSE")
                break
        self._failures[provider.provider_name] = self._failures.get(provider.provider_name, 0) + 1
        completed = self.clock()
        return ProviderResult(
            provider=provider.provider_name,
            requirement_key=requirement.key,
            failure=ProviderFailure(
                provider=provider.provider_name,
                requirement_key=requirement.key,
                reason=last_error.code,
                retryable=last_error.retryable,
                occurred_at=completed,
                attempt=min(self.max_retries + 1, 10),
            ),
            health=self._health(provider.provider_name),
            elapsed_ms=round((time.monotonic() - started) * 1000),
        )

    def _health(self, provider: str) -> ProviderHealth:
        failures = self._failures.get(provider, 0)
        status = "OPEN_CIRCUIT" if failures >= self.circuit_breaker_failures else "DEGRADED" if failures else "HEALTHY"
        return ProviderHealth(
            provider=provider,
            status=status,
            health_score=max(Decimal("0"), Decimal("1") - Decimal(failures) / Decimal(self.circuit_breaker_failures)),
            consecutive_failures=failures,
            last_success=self._last_success.get(provider),
        )

    def _cache_result(
        self, requirement: ResearchDataRequirement, records: tuple[EvidenceRecord, ...]
    ) -> ProviderResult:
        return ProviderResult(
            provider="local-research-cache",
            requirement_key=requirement.key,
            evidence=records,
            health=ProviderHealth(
                provider="local-research-cache",
                status="HEALTHY",
                health_score=Decimal("1"),
                consecutive_failures=0,
                last_success=self.clock(),
            ),
            elapsed_ms=0,
            cache_hit=True,
        )

    def _open_circuit(self, provider: str, requirement: ResearchDataRequirement) -> ProviderResult:
        return ProviderResult(
            provider=provider,
            requirement_key=requirement.key,
            failure=ProviderFailure(
                provider=provider,
                requirement_key=requirement.key,
                reason="PROVIDER_CIRCUIT_OPEN",
                occurred_at=self.clock(),
                attempt=1,
            ),
            health=self._health(provider),
            elapsed_ms=0,
        )

    @staticmethod
    def _expiry(category: DataCategory, retrieved_at: datetime) -> datetime:
        ttl = {
            DataCategory.MARKET_SNAPSHOT: timedelta(minutes=5),
            DataCategory.PRICE_HISTORY: timedelta(hours=18),
            DataCategory.VOLUME_HISTORY: timedelta(hours=18),
            DataCategory.BENCHMARK: timedelta(hours=18),
            DataCategory.FUNDAMENTALS: timedelta(days=3),
            DataCategory.VALUATION: timedelta(days=1),
            DataCategory.EARNINGS: timedelta(hours=12),
            DataCategory.NEWS: timedelta(hours=2),
            DataCategory.CORPORATE_ACTIONS: timedelta(days=1),
            DataCategory.MACRO: timedelta(hours=6),
            DataCategory.RATES: timedelta(hours=6),
        }.get(category, timedelta(hours=18))
        return retrieved_at + ttl

    @staticmethod
    def _derive(evidence: Sequence[EvidenceRecord], *, as_of: datetime) -> tuple[EvidenceRecord, ...]:
        histories: dict[str, EvidenceRecord] = {}
        for item in evidence:
            if (
                item.field in {"daily_ohlcv_1y", "daily_ohlcv", "benchmark_ohlcv_1y"}
                and isinstance(item.value, list)
            ):
                histories.setdefault(item.symbol, item)
        benchmark_record = histories.get("SPY")

        def bars(record: EvidenceRecord | None) -> tuple[Bar, ...]:
            if record is None or not isinstance(record.value, list):
                return ()
            parsed: list[Bar] = []
            for row in record.value:
                if not isinstance(row, dict):
                    continue
                try:
                    parsed.append(
                        Bar(
                            timestamp=datetime.fromisoformat(str(row["observed_at"])),
                            open=Decimal(str(row["open"])),
                            high=Decimal(str(row["high"])),
                            low=Decimal(str(row["low"])),
                            close=Decimal(str(row["close"])),
                            volume=int(Decimal(str(row["volume"]))),
                        )
                    )
                except (KeyError, ValueError, ArithmeticError):
                    continue
            return tuple(parsed)

        benchmark_bars = bars(benchmark_record)
        output: list[EvidenceRecord] = []
        volatility = {"realized_volatility_20d", "atr14", "drawdown"}
        volume = {"average_volume_20d", "relative_volume"}
        for symbol, history in histories.items():
            source_bars = bars(history)
            features = derive_market_features(
                source_bars,
                as_of=as_of,
                benchmark_bars=benchmark_bars if symbol not in {"SPY", "QQQ"} else (),
                qqq_bars=bars(histories.get("QQQ")) if symbol != "QQQ" else (),
            )
            for field, value in features.items():
                if value is None:
                    continue
                category = (
                    DataCategory.VOLATILITY
                    if field in volatility
                    else DataCategory.VOLUME_HISTORY
                    if field in volume
                    else DataCategory.TECHNICAL
                )
                output.append(
                    EvidenceRecord(
                        requirement_key=f"{symbol}:{category.value}:{field}",
                        field=field,
                        category=category,
                        value=str(value),
                        unit="PRICE" if field.startswith(("sma", "ema", "atr")) else "SHARES" if field == "average_volume_20d" else "OSCILLATOR_0_100" if field == "rsi14" else "RATIO",
                        symbol=symbol,
                        timestamp=source_bars[-1].timestamp,
                        as_of=as_of,
                        source="derived-from:" + (history.evidence_id or "UNKNOWN"),
                        source_type=SourceType.DETERMINISTIC_DERIVED,
                        retrieved_at=datetime.now(UTC),
                        provider="meridian-derived-market-features-v1",
                        confidence=history.confidence,
                        raw_reference="|".join(item.evidence_id or item.raw_reference for item in (history, *([benchmark_record] if benchmark_record else []), *([histories["QQQ"]] if "QQQ" in histories else []))),
                        validation_status=ValidationStatus.PASS,
                    )
                )
        return tuple(output)

    def _audit(self, package: ResearchEvidencePackage) -> None:
        if self.audit_root is None:
            return
        run = self.audit_root / package.created_at.strftime("%Y%m%dT%H%M%S%fZ")
        try:
            run.mkdir(parents=True, exist_ok=False)
            package_payload = package.model_dump(mode="json")
            for item in package_payload.get("evidence", []):
                if item.get("category") == DataCategory.PORTFOLIO_CONTEXT.value:
                    item["value"] = {
                        "redacted": True,
                        "in_memory_context_supplied": True,
                        "raw_account_persisted": False,
                    }
                    item["raw_reference"] = "REDACTED_PORTFOLIO_REFERENCE"
            artifacts: dict[str, Any] = {
                "data_requirements.json": [item.model_dump(mode="json") for item in package.requirements],
                "retrieval_plan.json": {
                    "provider_order": [item.provider_name for item in self.providers],
                    "max_retries": self.max_retries,
                    "rounds": package.rounds,
                },
                "provider_results.json": [item.model_dump(mode="json") for item in package.provider_results],
                "evidence_package.json": package_payload,
                "source_conflicts.json": [item.model_dump(mode="json") for item in package.conflicts],
            }
            for name, payload in artifacts.items():
                (run / name).write_text(
                    json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8"
                )
        except OSError:
            # Audit persistence cannot convert validated public evidence into missing evidence.
            return
