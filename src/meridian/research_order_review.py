"""Isolated paper planning via existing risk/reconciliation/order engines.

No ledger, broker, approval issuer or account persistence. Shadow research never
issues a production manual readiness certificate, even when paper drafts exist.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime, Field

from meridian.config import load_policies
from meridian.daily_closure import DailyClosureService
from meridian.execution_quotes import ExecutionQuote, ExecutionQuoteCapabilityCertificate
from meridian.manual_authority import _certificate_is_usable
from meridian.orders import OrderPlanner, ProjectedPortfolioValidator
from meridian.quant.backtest import pit_correlations
from meridian.quant.flagship_packet import build_flagship_packet
from meridian.quant.portfolio import challenger_budget_violations
from meridian.reconciliation import ReconciliationEngine
from meridian.research_terminal import (
    PortfolioWhatIfRequest,
    QuantTerminalRequest,
    fingerprint,
    flagship_policy,
    portfolio_what_if,
)
from meridian.risk import RiskEngine
from meridian.runtime import policy_directory
from meridian.schemas import AccountSnapshot, MarketSnapshot, OrderDraft, Side, StableModel
from meridian.security import AssetType, SecurityMetadata
from meridian.trading_calendar import session_context

D = Decimal


class ManualOrderTicket(StableModel):
    analysis_cutoff: AwareDatetime | None = None
    request_hash: str | None = None
    version: Literal['manual-order-ticket.v1'] = 'manual-order-ticket.v1'
    state: Literal['BLOCKED', 'PAPER_ONLY']
    engine: Literal['V2.3_SHADOW'] = 'V2.3_SHADOW'
    snapshot_hash: str | None
    paper_drafts: tuple[OrderDraft, ...] = Field(default=(), max_length=8)
    planning_status: Literal['BLOCKED', 'NO_ACTION', 'DRAFTS_AVAILABLE']
    order_trace: dict = Field(default_factory=dict)
    blockers: tuple[str, ...]
    manual_blockers: tuple[str, ...] = ('SHADOW_STRATEGY_NOT_PROMOTED', 'SEALED_SEVEN_GATE_MANUAL_AUTHORITY_REQUIRED', 'HUMAN_APPROVAL_REQUIRED')
    limit_source: Literal['EXISTING_ORDER_PLANNER_NOT_RESEARCH_ZONE'] = 'EXISTING_ORDER_PLANNER_NOT_RESEARCH_ZONE'
    fills: tuple[()] = ()
    broker_submission: Literal['DISABLED'] = 'DISABLED'
    execution_authority: Literal['NONE'] = 'NONE'


class PaperReviewRequest(StableModel):
    quant: QuantTerminalRequest
    account: AccountSnapshot | None = Field(default=None, exclude=True, repr=False)
    planner_quotes: tuple[MarketSnapshot, ...] = Field(default=(), max_length=8)
    execution_quotes: tuple[ExecutionQuote, ...] = Field(default=(), max_length=8)
    certificates: tuple[ExecutionQuoteCapabilityCertificate, ...] = Field(default=(), max_length=8)


def review_paper_request(request: PaperReviewRequest) -> ManualOrderTicket:
    if len({q.ticker for q in request.planner_quotes}) != len(request.planner_quotes):
        raise ValueError('PAPER_REVIEW_DUPLICATE_PLANNER_QUOTE')
    return plan_paper_review(request.quant, account=request.account,
        quotes={q.ticker:q for q in request.planner_quotes}, execution_quotes=request.execution_quotes,
        certificates=request.certificates)


def plan_paper_review(request: QuantTerminalRequest, *, account: AccountSnapshot | None,
                      quotes: dict[str, MarketSnapshot] | None = None,
                      execution_quotes: tuple[ExecutionQuote, ...] = (),
                      certificates: tuple[ExecutionQuoteCapabilityCertificate, ...] = ()) -> ManualOrderTicket:
    result = _plan_paper_review(request, account=account, quotes=quotes, execution_quotes=execution_quotes, certificates=certificates)
    return result.model_copy(update={'analysis_cutoff':request.analysis_cutoff, 'request_hash':fingerprint(request)})


def _plan_paper_review(request: QuantTerminalRequest, *, account: AccountSnapshot | None,
                      quotes: dict[str, MarketSnapshot] | None = None,
                      execution_quotes: tuple[ExecutionQuote, ...] = (),
                      certificates: tuple[ExecutionQuoteCapabilityCertificate, ...] = ()) -> ManualOrderTicket:
    request = QuantTerminalRequest.model_validate(request.model_dump())
    if request.engine != 'V2.3_SHADOW':
        raise ValueError('PAPER_REVIEW_EXPLICIT_V23_ENGINE_REQUIRED')
    policies = load_policies(policy_directory())
    cutoff = request.analysis_cutoff
    blockers = []
    trace: dict[str, dict[str, object]] = {}
    if account is None:
        blockers.append('FRESH_AUTHORIZED_ACCOUNT_REQUIRED')
    else:
        account = AccountSnapshot.model_validate(account.model_dump())
        context = portfolio_what_if(PortfolioWhatIfRequest(analysis_cutoff=cutoff, account=account,
            desired=(), metadata=request.metadata))
        if context.status == 'BLOCKED':
            blockers.extend(context.violations)
    if session_context(cutoff) != 'REGULAR':
        blockers.append('REGULAR_SESSION_REQUIRED_FOR_PAPER_PLAN')
    if len(execution_quotes) > 8 or len(certificates) > 8 or len(quotes or {}) > 8:
        raise ValueError('PAPER_PLAN_QUOTE_LIMIT_8')
    if len({q.symbol for q in execution_quotes}) != len(execution_quotes) or len({c.certificate_id for c in certificates}) != len(certificates):
        raise ValueError('PAPER_PLAN_DUPLICATE_QUOTE_OR_CERTIFICATE')
    execution = {q.symbol: q for q in execution_quotes}
    certs = {c.certificate_id: c for c in certificates}
    market = {s: MarketSnapshot.model_validate(q.model_dump()) for s, q in (quotes or {}).items()}
    required = set(request.symbols) | ({h.ticker for h in account.holdings} if account else set())
    for symbol in sorted(required):
        quote = execution.get(symbol)
        cert = certs.get(quote.certificate_id) if quote else None
        supplied = market.get(symbol)
        if quote is None or cert is None or supplied is None:
            blockers.append(symbol + ':CERTIFIED_EXECUTION_AND_PLANNER_INPUT_REQUIRED')
            continue
        usable, reason = _certificate_is_usable(quote, cert, now=cutoff, symbol=symbol,
            max_spread=policies.execution.max_spread_percent)
        if not usable:
            blockers.append(symbol + ':' + reason)
        if supplied.ticker != symbol or (supplied.last, supplied.bid, supplied.ask, supplied.timestamp) != (quote.last, quote.bid, quote.ask, quote.timestamp):
            blockers.append(symbol + ':EXECUTION_PLANNER_QUOTE_IDENTITY_MISMATCH')
    if account:
        blockers.extend(DailyClosureService(policies)._gates(account, market, cutoff))
    if blockers or account is None:
        return ManualOrderTicket(state='BLOCKED', snapshot_hash=None, planning_status='BLOCKED', blockers=tuple(dict.fromkeys(blockers)))
    history = {h.canonical_symbol: h for h in request.histories}
    if required - history.keys():
        return ManualOrderTicket(state='BLOCKED', snapshot_hash=None, planning_status='BLOCKED', blockers=('HELD_AND_TARGET_HISTORY_REQUIRED',))
    metadata = {m.symbol: SecurityMetadata(m.symbol, AssetType(m.asset_type), m.sector, None) for m in request.metadata}
    if required - metadata.keys():
        return ManualOrderTicket(state='BLOCKED', snapshot_hash=None, planning_status='BLOCKED', blockers=('HELD_AND_TARGET_METADATA_REQUIRED',))
    current = {h.ticker: h.market_value / account.total_equity for h in account.holdings}
    policy = flagship_policy()
    from meridian.quant.policy import CostPolicy
    try:
        packet = build_flagship_packet(history, cutoff, symbols=request.symbols, current=current, nav=account.total_equity,
            risk=policies.risk, policy=policy, costs=CostPolicy(), sector_map={s: m.sector for s, m in metadata.items()},
            asset_types={s: m.asset_type.value for s, m in metadata.items()}, diagnostic=False)
    except ValueError:
        return ManualOrderTicket(state='BLOCKED', snapshot_hash=None, planning_status='BLOCKED', blockers=('QUALIFIED_NON_SYNTHETIC_HISTORY_REQUIRED',))
    rebalance = packet.cost_adjusted_proposal
    if rebalance.action != 'REBALANCE':
        return ManualOrderTicket(state='PAPER_ONLY' if rebalance.action == 'NO_ACTION' else 'BLOCKED', snapshot_hash=packet.digest,
            planning_status='NO_ACTION' if rebalance.action == 'NO_ACTION' else 'BLOCKED', blockers=rebalance.reasons)
    risk = RiskEngine().approve(rebalance.target, account, 'NORMAL', policies.risk, metadata=metadata)
    if risk.violations:
        return ManualOrderTicket(state='BLOCKED', snapshot_hash=packet.digest, planning_status='BLOCKED', blockers=risk.violations)
    reconciliation = ReconciliationEngine().reconcile(account, risk.approved)
    drafts = OrderPlanner().plan(account, reconciliation, market, policies.execution, policies.risk, account.total_equity, trace=trace)
    validator = ProjectedPortfolioValidator()
    base = {f.base.symbol: f.base for f in packet.features}
    correlations = pit_correlations(history, cutoff, policy.baseline.controls.correlation_lookback)
    # No sell fill is assumed. Check the complete draft set and the all-buys/no-sells state.
    for group in (drafts, tuple(d for d in drafts if d.side is Side.BUY)):
        projection = validator.validate(account, group, account.total_equity, policies.risk.min_cash_weight,
            policies.risk.max_position_weight, policies.risk.max_number_positions,
            sector_map={s: m.sector for s, m in metadata.items() if m.sector}, max_sector_weight=policies.risk.max_sector_weight)
        blockers.extend(projection.violations)
        post = dict(current)
        for draft in group:
            post[draft.ticker] = post.get(draft.ticker, D(0)) + draft.estimated_notional / account.total_equity * (1 if draft.side is Side.BUY else -1)
        friction_nav = account.total_equity - CostPolicy().estimate(sum((d.estimated_notional for d in group), D(0)), len(group))
        cash_after = account.cash + sum((d.estimated_notional * (1 if d.side is Side.SELL else -1) for d in group), D(0)) - (account.total_equity - friction_nav)
        if cash_after < 0 or cash_after < friction_nav * policies.risk.min_cash_weight:
            blockers.append('FRICTION_ADJUSTED_CASH_RESERVE_VIOLATION')
        if friction_nav <= 0:
            blockers.append('FRICTION_ADJUSTED_NAV_NONPOSITIVE')
        else:
            post = {s: w * account.total_equity / friction_nav for s, w in post.items() if w > 0}
            blockers.extend(challenger_budget_violations(post, base, correlations, policies.risk, policy.baseline, packet.regime))
    for symbol in required:
        if trace.get(symbol, {}).get('reason') not in {'DRAFT', 'NO_RECONCILIATION_DELTA', None}:
            blockers.append(symbol + ':' + str(trace[symbol]['reason']))
    return ManualOrderTicket(state='BLOCKED' if blockers else 'PAPER_ONLY', snapshot_hash=packet.digest,
        planning_status='BLOCKED' if blockers else 'DRAFTS_AVAILABLE' if drafts else 'NO_ACTION',
        paper_drafts=() if blockers else drafts, order_trace=trace, blockers=tuple(dict.fromkeys(blockers)))
