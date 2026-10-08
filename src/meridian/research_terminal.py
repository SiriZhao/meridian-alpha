"""Read-only terminal contracts over existing Quant and risk engines.

No provider, database, subprocess, filesystem write or order planner lives here.
Caller attestation is not authentication or financial OOS eligibility.
"""
from __future__ import annotations

import hashlib
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, model_validator

from meridian.config import Policies, load_policies
from meridian.historical import HistoricalBarSeries
from meridian.quant.backtest import QuantSecurityMetadata
from meridian.quant.numerics import deterministic_decimal
from meridian.quant.packet import QuantResearchPacketV22, build_research_packet
from meridian.quant.policy import ChallengerPolicy, CostPolicy
from meridian.quant.portfolio import target_from_weights, weights
from meridian.quant.regime import RegimeState
from meridian.quant.signals import ChallengerScore
from meridian.quant.version import ENGINE_SOURCE_HASH
from meridian.risk import RiskEngine
from meridian.runtime import policy_directory
from meridian.schemas import AccountSnapshot, AccountSyncState, FreshnessState, StableModel
from meridian.security import AssetType, SecurityMetadata

D = Decimal
Symbol = Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,14}$")]
Hash = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Fraction = Annotated[Decimal, Field(ge=0, le=1, allow_inf_nan=False)]


def fingerprint(value: StableModel) -> str:
    return hashlib.sha256(value.stable_json().encode()).hexdigest()


class QuantTerminalRequest(StableModel):
    analysis_cutoff: AwareDatetime
    symbols: tuple[Symbol, ...] = Field(min_length=1, max_length=8)
    histories: tuple[HistoricalBarSeries, ...] = Field(max_length=9)
    metadata: tuple[QuantSecurityMetadata, ...] = Field(default=(), max_length=9)
    diagnostic: bool = False

    @model_validator(mode="after")
    def bounded_identity(self) -> QuantTerminalRequest:
        names = [h.canonical_symbol for h in self.histories]
        if len(set(self.symbols)) != len(self.symbols) or len(set(names)) != len(names):
            raise ValueError("TERMINAL_DUPLICATE_SYMBOL")
        if set(names) - set(self.symbols) - {"SPY"}:
            raise ValueError("TERMINAL_UNREQUESTED_HISTORY")
        if any(len(h.bars) > 800 for h in self.histories):
            raise ValueError("TERMINAL_HISTORY_LIMIT_800")
        if len(self.stable_json().encode()) > 2000000:
            raise ValueError("TERMINAL_INPUT_BYTE_LIMIT_2MB")
        if any(m.known_at.tzinfo is None or m.known_at > self.analysis_cutoff for m in self.metadata):
            raise ValueError("TERMINAL_METADATA_FUTURE_OR_NAIVE")
        return self


class QuantTerminalRow(StableModel):
    symbol: Symbol
    evidence_id: str
    score: Decimal | None
    rank: int | None
    quality: str
    eligible: bool
    reasons: tuple[str, ...]
    chinese_explanation: str


class QuantTerminalSnapshot(StableModel):
    schema_version: Literal["meridian-quant-terminal.v1"] = "meridian-quant-terminal.v1"
    status: Literal["AVAILABLE", "SYNTHETIC_DIAGNOSTIC", "BLOCKED"]
    analysis_cutoff: AwareDatetime
    request_hash: Hash
    input_hashes: dict[str, str]
    policy_hash: Hash
    risk_policy_hash: Hash
    engine_hash: Hash
    packet: QuantResearchPacketV22 | None
    rows: tuple[QuantTerminalRow, ...]
    reasons: tuple[str, ...]
    source: Literal["CALLER_SUPPLIED_HISTORY"] = "CALLER_SUPPLIED_HISTORY"
    freshness: Literal["AS_OF_CUTOFF_SEE_FACTOR_AVAILABILITY"] = "AS_OF_CUTOFF_SEE_FACTOR_AVAILABILITY"
    certification: str
    predictive_confidence: None = None
    financial_oos_eligible: Literal[False] = False
    execution_authority: Literal["NONE"] = "NONE"
    broker_submission: Literal["DISABLED"] = "DISABLED"

    @property
    def digest(self) -> str:
        return fingerprint(self)


class QuantModelRow(StableModel):
    signal: QuantTerminalRow
    quant: ChallengerScore | None
    desired_weight: Decimal
    feasible_weight: Decimal


class QuantModelView(StableModel):
    """Compact numerical evidence before inference; full factors remain in MCP."""
    version: Literal["terminal-quant-model-view.v1"] = "terminal-quant-model-view.v1"
    analysis_cutoff: AwareDatetime
    snapshot_hash: Hash
    engine_hash: Hash
    policy_hash: Hash
    risk_policy_hash: Hash
    input_hashes: dict[str, str]
    certification: str
    rows: tuple[QuantModelRow, ...] = Field(max_length=8)
    regime: RegimeState | None
    unknowns: tuple[str, ...]
    execution_authority: Literal["NONE"] = "NONE"
    financial_oos_eligible: Literal[False] = False

    @model_validator(mode="after")
    def coherent_cutoff_and_identity(self) -> QuantModelView:
        if len({r.signal.symbol for r in self.rows}) != len(self.rows) or len({r.signal.evidence_id for r in self.rows}) != len(self.rows):
            raise ValueError("TERMINAL_MODEL_DUPLICATE_IDENTITY")
        if self.regime and self.regime.as_of != self.analysis_cutoff:
            raise ValueError("TERMINAL_MODEL_REGIME_CUTOFF_MISMATCH")
        for row in self.rows:
            if row.quant:
                score = row.quant
                if score.bridge.as_of != self.analysis_cutoff or score.bridge.symbol != row.signal.symbol or score.policy_hash != self.policy_hash:
                    raise ValueError("TERMINAL_MODEL_SCORE_CUTOFF_OR_IDENTITY_MISMATCH")
                if any(c.as_of != self.analysis_cutoff or c.availability_cutoff > self.analysis_cutoff
                       or c.symbol != row.signal.symbol for c in score.factor_attribution):
                    raise ValueError("TERMINAL_MODEL_FACTOR_CUTOFF_OR_IDENTITY_MISMATCH")
                if row.signal.eligible and (score.bridge.exclusion_reasons or row.signal.score != score.bridge.quant_score
                        or row.signal.rank != score.bridge.relative_rank or row.signal.quality == "REJECTED"):
                    raise ValueError("TERMINAL_MODEL_SIGNAL_SCORE_MISMATCH")
            if not row.signal.eligible and (row.signal.score is not None or row.signal.rank is not None):
                raise ValueError("TERMINAL_MODEL_INELIGIBLE_RANK_OR_SCORE")
        return self


class EvidenceTraceRequest(StableModel):
    request: QuantTerminalRequest
    evidence_id: str = Field(min_length=1, max_length=160)


class EvidenceTraceResult(StableModel):
    version: Literal["terminal-evidence-trace.v1"] = "terminal-evidence-trace.v1"
    status: Literal["FOUND", "NOT_FOUND"]
    analysis_cutoff: AwareDatetime
    evidence_id: str
    snapshot_hash: Hash
    source_hashes: dict[str, str]
    symbol_result: dict | None
    reason: str | None
    source: Literal["RECOMPUTED_DETERMINISTIC_QUANT"] = "RECOMPUTED_DETERMINISTIC_QUANT"
    execution_authority: Literal["NONE"] = "NONE"


def research_evidence_trace(request: EvidenceTraceRequest) -> EvidenceTraceResult:
    snapshot = quant_terminal_snapshot(request.request)
    row = next((r for r in snapshot.rows if r.evidence_id == request.evidence_id), None)
    raw = next((r for r in snapshot.packet.symbols if row and r.symbol == row.symbol), None) if snapshot.packet else None
    return EvidenceTraceResult(status="FOUND" if row else "NOT_FOUND", analysis_cutoff=snapshot.analysis_cutoff,
        evidence_id=request.evidence_id, snapshot_hash=snapshot.digest, source_hashes=snapshot.input_hashes,
        symbol_result=raw.model_dump(mode="json") if raw else row.model_dump(mode="json") if row else None,
        reason=None if row else "EVIDENCE_ID_NOT_IN_THIS_CUTOFF_AND_INPUT_SET")


def challenger_policy() -> ChallengerPolicy:
    import yaml
    return ChallengerPolicy.model_validate(yaml.safe_load(
        (policy_directory() / "quant-v22.yaml").read_text(encoding="utf-8")))


def risk_policy_fingerprint(policies: Policies | None = None) -> str:
    return hashlib.sha256((policies or load_policies(policy_directory())).risk.model_dump_json().encode()).hexdigest()


def quant_terminal_snapshot(request: QuantTerminalRequest) -> QuantTerminalSnapshot:
    # Revalidation also protects direct Python callers using model_copy/update.
    request = QuantTerminalRequest.model_validate(request.model_dump())
    policy = challenger_policy()
    policies = load_policies(policy_directory())
    histories = {h.canonical_symbol: h for h in request.histories}
    missing = sorted((set(request.symbols) | {"SPY"}) - histories.keys())
    reasons = tuple("HISTORY_REQUIRED:" + s for s in missing)
    packet = None
    if not missing:
        try:
            packet = build_research_packet(histories, request.symbols,
                cutoff=request.analysis_cutoff, policies=policies,
                policy=policy, metadata=request.metadata, diagnostic=request.diagnostic)
        except ValueError:
            # Do not echo provider text, private values or arbitrary exception input.
            reasons = ("HISTORY_CONTRACT_OR_ENGINE_REJECTED",)
    qualified = packet is not None and packet.data_certification_class in {
        "CERTIFIED_RESEARCH_PIT_ADJUSTED", "SYNTHETIC_DIAGNOSTIC"}
    rows = []
    key = fingerprint(request)
    row_map = {r.symbol: r for r in packet.symbols} if packet else {}
    for symbol in sorted(request.symbols):
        raw = row_map.get(symbol)
        eligible = bool(qualified and raw and raw.score and not raw.score.bridge.exclusion_reasons)
        score = raw.score.bridge if raw and raw.score else None
        excluded = tuple(score.exclusion_reasons) if score else reasons
        rows.append(QuantTerminalRow(symbol=symbol, evidence_id="terminal-" + key + "-" + symbol,
            score=score.quant_score if eligible and score else None,
            rank=score.relative_rank if eligible and score else None,
            quality=raw.feature.base.quality_status if raw else "MISSING", eligible=eligible,
            reasons=excluded, chinese_explanation="仅供影子研究；" + (
                "因子已计算，排名不代表获利概率。" if eligible else "等待证据：" + "、".join(excluded))))
    certification = packet.data_certification_class if packet else "UNKNOWN"
    if not qualified and not reasons:
        reasons = ("INSUFFICIENT_VERIFIED_HISTORY",)
    return QuantTerminalSnapshot(status="SYNTHETIC_DIAGNOSTIC" if qualified and certification == "SYNTHETIC_DIAGNOSTIC"
        else "AVAILABLE" if qualified else "BLOCKED", analysis_cutoff=request.analysis_cutoff,
        request_hash=key, input_hashes={s: h.stable_hash for s, h in sorted(histories.items())},
        policy_hash=policy.digest, risk_policy_hash=risk_policy_fingerprint(policies), engine_hash=ENGINE_SOURCE_HASH, packet=packet,
        rows=tuple(rows), reasons=reasons, certification=certification)


class HypotheticalWeight(StableModel):
    symbol: Symbol
    weight: Fraction


class DeclaredShock(StableModel):
    symbol: Symbol
    return_shock: Decimal = Field(ge=-1, le=1, allow_inf_nan=False)


class PortfolioWhatIfRequest(StableModel):
    analysis_cutoff: AwareDatetime
    # Not persisted, logged, cached or echoed. This is the caller's actual snapshot.
    account: AccountSnapshot = Field(exclude=True, repr=False)
    desired: tuple[HypotheticalWeight, ...] = Field(max_length=20)
    metadata: tuple[QuantSecurityMetadata, ...] = Field(default=(), max_length=40)
    shocks: tuple[DeclaredShock, ...] = Field(default=(), max_length=40)

    @model_validator(mode="after")
    def coherent(self) -> PortfolioWhatIfRequest:
        if self.account.account_alias != "Schwab-Paper":
            raise ValueError("TERMINAL_SCHWAB_PAPER_ONLY")
        if len(self.account.holdings) > 40 or len(self.account.recent_investment_transactions) > 40:
            raise ValueError("TERMINAL_ACCOUNT_PAYLOAD_LIMIT_40")
        for items in (self.desired, self.shocks, self.metadata):
            if len({i.symbol for i in items}) != len(items):
                raise ValueError("TERMINAL_DUPLICATE_IDENTITY")
        if sum((p.weight for p in self.desired), D(0)) > 1:
            raise ValueError("TERMINAL_NO_LEVERAGE")
        if any(m.known_at.tzinfo is None or m.known_at > self.analysis_cutoff for m in self.metadata):
            raise ValueError("TERMINAL_METADATA_FUTURE_OR_NAIVE")
        return self


class PortfolioWhatIfResult(StableModel):
    schema_version: Literal["meridian-portfolio-what-if.v1"] = "meridian-portfolio-what-if.v1"
    status: Literal["RESEARCH_ONLY", "BLOCKED"]
    analysis_cutoff: AwareDatetime
    current: dict[str, Decimal]
    preferred: dict[str, Decimal]
    feasible: dict[str, Decimal]
    cash_weight_before: Decimal | None
    cash_weight_after: Decimal | None
    feasible_turnover: Decimal | None
    estimated_cost_fraction: Decimal | None
    current_declared_shock_return: Decimal | None
    feasible_declared_shock_return: Decimal | None
    violations: tuple[str, ...]
    modifications: tuple[str, ...]
    unknowns: tuple[str, ...]
    policy_hash: Hash
    source: Literal["AUTHORIZED_IN_MEMORY_PAPER_SNAPSHOT"] = "AUTHORIZED_IN_MEMORY_PAPER_SNAPSHOT"
    freshness: str
    execution_authority: Literal["NONE"] = "NONE"
    broker_submission: Literal["DISABLED"] = "DISABLED"


@deterministic_decimal
def portfolio_what_if(request: PortfolioWhatIfRequest) -> PortfolioWhatIfResult:
    # exclude=True is intentional privacy. Validate the private field explicitly.
    request = PortfolioWhatIfRequest.model_validate({**request.model_dump(), "account": request.account.model_dump()})
    policies = load_policies(policy_directory())
    account = request.account
    age = (request.analysis_cutoff - account.as_of).total_seconds() if account.as_of.tzinfo else -1
    blockers = []
    if account.currency != "USD":
        blockers.append("ACCOUNT_USD_REQUIRED")
    if age < 0 or age > policies.data.account_snapshot_max_age_seconds:
        blockers.append("ACCOUNT_FUTURE_NAIVE_OR_STALE")
    if account.sync_state != AccountSyncState.SYNCED or account.freshness_state not in {FreshnessState.RECENT, FreshnessState.VERIFIED}:
        blockers.append("ACCOUNT_FRESH_SYNC_REQUIRED")
    nav = account.total_equity
    if nav <= 0 or abs(account.cash + sum((h.market_value for h in account.holdings), D(0)) - nav) > D("0.01"):
        blockers.append("ACCOUNT_NAV_INCONSISTENT_OR_NONPOSITIVE")
    desired = {p.symbol: p.weight for p in request.desired if p.weight > 0}
    metadata = {m.symbol: SecurityMetadata(m.symbol, AssetType(m.asset_type), m.sector, None) for m in request.metadata}
    current = {} if blockers else {h.ticker: h.market_value / nav for h in account.holdings}
    feasible: dict[str, Decimal] = {}
    violations: tuple[str, ...] = tuple(blockers)
    modifications: tuple[str, ...] = ()
    if not blockers:
        target = target_from_weights(desired, request.analysis_cutoff, "TERMINAL_HYPOTHETICAL")
        approved = RiskEngine().approve(target, account, "NORMAL", policies.risk, metadata=metadata)
        feasible = weights(approved.approved)
        violations, modifications = approved.violations, approved.modifications
    turnover = sum((abs(feasible.get(s, D(0)) - current.get(s, D(0))) for s in current.keys() | feasible.keys()), D(0)) if not blockers else None
    count = sum(feasible.get(s, D(0)) != current.get(s, D(0)) for s in current.keys() | feasible.keys())
    shocks = {s.symbol: s.return_shock for s in request.shocks}
    shock_complete = bool(shocks) and (current.keys() | feasible.keys()) <= shocks.keys()
    unknowns = ["NO_ORDERS_OR_FILL_ASSUMPTION", "QUOTE_AND_WHOLE_SHARE_FEASIBILITY_NOT_EVALUATED",
        "EXPECTED_RETURN_UNCALIBRATED", "SPREAD_UNKNOWN", "ETF_LOOKTHROUGH_UNKNOWN", "CORRELATION_NOT_SUPPLIED"]
    if not shock_complete:
        unknowns.append("SHOCK_COVERAGE_INCOMPLETE_OR_NOT_REQUESTED")
    if turnover is not None and turnover > policies.risk.max_daily_turnover:
        unknowns.append("HYPOTHETICAL_TURNOVER_EXCEEDS_DAILY_LIMIT_NO_ELIGIBLE_CHANGE")
    if any(abs(feasible.get(s, D(0)) - current.get(s, D(0))) * nav < policies.execution.minimum_order_notional
           for s in current.keys() | feasible.keys() if feasible.get(s, D(0)) != current.get(s, D(0))):
        unknowns.append("HYPOTHETICAL_CHANGE_BELOW_MINIMUM_NOTIONAL")
    return PortfolioWhatIfResult(status="BLOCKED" if blockers else "RESEARCH_ONLY", analysis_cutoff=request.analysis_cutoff,
        current=current, preferred=desired, feasible=feasible,
        cash_weight_before=account.cash / nav if not blockers else None,
        cash_weight_after=1 - sum(feasible.values(), D(0)) if not blockers else None,
        feasible_turnover=turnover,
        estimated_cost_fraction=CostPolicy().estimate(turnover * nav, count) / nav if turnover is not None else None,
        current_declared_shock_return=sum((w * shocks[s] for s, w in current.items()), D(0)) if shock_complete else None,
        feasible_declared_shock_return=sum((w * shocks[s] for s, w in feasible.items()), D(0)) if shock_complete else None,
        violations=violations, modifications=modifications, unknowns=tuple(unknowns),
        policy_hash=hashlib.sha256(policies.risk.model_dump_json().encode()).hexdigest(),
        freshness=account.freshness_state.value)
