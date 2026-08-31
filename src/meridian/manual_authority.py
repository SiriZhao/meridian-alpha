"""The single sealed authority for a real manual-order draft.

Legacy analysis and fixture order planners may still produce diagnostic
``OrderDraft`` values, but this module is the only path that can issue a
production-shaped ``ManualOrderDraft``.  It requires all seven readiness gates,
an identity-bound execution quote, and a complete capability certificate.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import Field, model_validator

from meridian.execution_quotes import (
    ExecutionQuote,
    ExecutionQuoteCapabilityCertificate,
    ExecutionSession,
    ManualLimitPricePolicy,
)
from meridian.schemas import Side, StableModel


class ManualReadinessStatus(StrEnum):
    READY = "READY"
    BLOCKED = "BLOCKED"


_REQUIRED_GATES = (
    "ACCOUNT_READY",
    "SECURITY_READY",
    "MARKET_READY",
    "RESEARCH_READY",
    "QUOTE_READY",
    "RISK_READY",
    "RECONCILIATION_READY",
)


class ManualReadinessCertificate(StableModel):
    """Immutable proof that every manual-entry prerequisite passed."""

    certificate_id: str = Field(min_length=1, max_length=160)
    run_id: str = Field(min_length=1, max_length=160)
    decision_as_of: datetime
    account_snapshot_hash: str = Field(min_length=1, max_length=128)
    security_master_manifest_hash: str = Field(min_length=1, max_length=128)
    market_state_hash: str = Field(min_length=1, max_length=128)
    research_state_hash: str = Field(min_length=1, max_length=128)
    execution_quote_certificate_id: str = Field(min_length=1, max_length=160)
    risk_state_hash: str = Field(min_length=1, max_length=128)
    reconciliation_state_hash: str = Field(min_length=1, max_length=128)
    policy_hash: str = Field(min_length=1, max_length=128)
    account_ready: bool = False
    security_ready: bool = False
    market_ready: bool = False
    research_ready: bool = False
    quote_ready: bool = False
    risk_ready: bool = False
    reconciliation_ready: bool = False
    issued_at: datetime
    status: ManualReadinessStatus = ManualReadinessStatus.BLOCKED
    blockers: tuple[str, ...] = ()

    @property
    def gates(self) -> dict[str, bool]:
        return {
            "ACCOUNT_READY": self.account_ready,
            "SECURITY_READY": self.security_ready,
            "MARKET_READY": self.market_ready,
            "RESEARCH_READY": self.research_ready,
            "QUOTE_READY": self.quote_ready,
            "RISK_READY": self.risk_ready,
            "RECONCILIATION_READY": self.reconciliation_ready,
        }

    @property
    def certificate_hash(self) -> str:
        return hashlib.sha256(self.stable_json().encode()).hexdigest()

    @model_validator(mode="after")
    def enforce_seven_gate_authority(self) -> ManualReadinessCertificate:
        if self.issued_at < self.decision_as_of:
            raise ValueError("MANUAL_READINESS_ISSUED_BEFORE_DECISION_CUTOFF")
        passed = all(self.gates.values())
        if self.status is ManualReadinessStatus.READY:
            if not passed:
                raise ValueError("MANUAL_READINESS_REQUIRES_ALL_SEVEN_GATES")
            if self.blockers:
                raise ValueError("MANUAL_READINESS_READY_HAS_BLOCKERS")
            for field_name in ("account_snapshot_hash", "security_master_manifest_hash", "market_state_hash", "research_state_hash", "risk_state_hash", "reconciliation_state_hash", "policy_hash"):
                value = getattr(self, field_name)
                if value in {"", "UNAVAILABLE", "UNKNOWN", "NONE"}:
                    raise ValueError(f"MANUAL_READINESS_PROVENANCE_MISSING:{field_name}")
                try:
                    if len(value) != 64:
                        raise ValueError
                    int(value, 16)
                except (TypeError, ValueError) as error:
                    raise ValueError(f"MANUAL_READINESS_PROVENANCE_INVALID:{field_name}") from error
            if self.execution_quote_certificate_id in {"", "UNVERIFIED", "NONE"}:
                raise ValueError("MANUAL_READINESS_QUOTE_CERTIFICATE_REQUIRED")
        return self


def issue_manual_readiness_certificate(
    *,
    certificate_id: str,
    run_id: str,
    decision_as_of: datetime,
    issued_at: datetime,
    hashes: Mapping[str, str],
    gates: Mapping[str, str | bool],
    execution_quote_certificate_id: str = "UNVERIFIED",
) -> ManualReadinessCertificate:
    """Issue READY only for seven literal PASS/True gates; all else blocks."""
    values: dict[str, bool] = {}
    blockers: list[str] = []
    for name in _REQUIRED_GATES:
        raw = gates.get(name, False)
        passed = raw is True or (isinstance(raw, str) and raw.upper() == "PASS")
        values[name] = passed
        if not passed:
            blockers.append(f"{name}:{str(raw).upper()}")
    status = ManualReadinessStatus.READY if not blockers else ManualReadinessStatus.BLOCKED
    required_hashes = {
        "account_snapshot_hash": hashes.get("account_snapshot_hash", "UNAVAILABLE"),
        "security_master_manifest_hash": hashes.get("security_master_manifest_hash", "UNAVAILABLE"),
        "market_state_hash": hashes.get("market_state_hash", "UNAVAILABLE"),
        "research_state_hash": hashes.get("research_state_hash", "UNAVAILABLE"),
        "risk_state_hash": hashes.get("risk_state_hash", "UNAVAILABLE"),
        "reconciliation_state_hash": hashes.get("reconciliation_state_hash", "UNAVAILABLE"),
        "policy_hash": hashes.get("policy_hash", "UNAVAILABLE"),
    }
    return ManualReadinessCertificate(
        certificate_id=certificate_id,
        run_id=run_id,
        decision_as_of=decision_as_of,
        issued_at=issued_at,
        execution_quote_certificate_id=execution_quote_certificate_id,
        **required_hashes,
        account_ready=values["ACCOUNT_READY"],
        security_ready=values["SECURITY_READY"],
        market_ready=values["MARKET_READY"],
        research_ready=values["RESEARCH_READY"],
        quote_ready=values["QUOTE_READY"],
        risk_ready=values["RISK_READY"],
        reconciliation_ready=values["RECONCILIATION_READY"],
        status=status,
        blockers=tuple(blockers),
    )


class ManualOrderDraft(StableModel):
    """Human-facing, non-executed draft sealed to readiness and quote IDs."""

    draft_id: str = Field(min_length=1, max_length=160)
    run_id: str = Field(min_length=1, max_length=160)
    readiness_certificate_id: str = Field(min_length=1, max_length=160)
    symbol: str = Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,15}$")
    side: Side
    quantity: Decimal = Field(gt=0)
    limit_price: Decimal = Field(gt=0)
    time_in_force_recommendation: str = Field(pattern=r"^(DAY|GTC)$")
    quote_id: str = Field(min_length=1, max_length=160)
    quote_provider: str = Field(min_length=1, max_length=128)
    quote_timestamp: datetime
    quote_certificate_id: str = Field(min_length=1, max_length=160)
    target_weight: Decimal = Field(ge=0, le=1)
    current_weight: Decimal = Field(ge=0, le=1)
    target_quantity: Decimal = Field(ge=0)
    current_quantity: Decimal = Field(ge=0)
    risk_checks: tuple[str, ...] = ()
    created_at: datetime
    status: str = "NOT_EXECUTED"

    @model_validator(mode="after")
    def never_execute(self) -> ManualOrderDraft:
        if self.status != "NOT_EXECUTED":
            raise ValueError("MANUAL_DRAFT_MUST_REMAIN_NOT_EXECUTED")
        return self


def _certificate_is_usable(
    quote: ExecutionQuote,
    certificate: ExecutionQuoteCapabilityCertificate,
    *,
    now: datetime,
    symbol: str,
    max_spread: Decimal = Decimal("0.02"),
) -> tuple[bool, str]:
    if now.tzinfo is None or now.utcoffset() is None:
        return False, "QUOTE_VALIDATION_TIMEZONE_REQUIRED"
    if max_spread <= 0:
        return False, "QUOTE_SPREAD_POLICY_INVALID"
    if not certificate.execution_quote_grade:
        return False, "BLOCKED_QUOTE_NOT_CERTIFIED"
    if not (certificate.bid and certificate.ask and certificate.last and certificate.timestamp_semantics_verified):
        return False, "BLOCKED_QUOTE_CAPABILITY_INCOMPLETE"
    if certificate.provider != quote.provider:
        return False, "QUOTE_PROVIDER_CERTIFICATE_MISMATCH"
    if quote.feed is not None and quote.feed != certificate.feed:
        return False, "QUOTE_FEED_CERTIFICATE_MISMATCH"
    if quote.plan is not None and quote.plan != certificate.plan:
        return False, "QUOTE_PLAN_CERTIFICATE_MISMATCH"
    if quote.certificate_id != certificate.certificate_id:
        return False, "QUOTE_CERTIFICATE_ID_MISMATCH"
    if certificate.certificate_id in {"", "UNSPECIFIED", "UNVERIFIED"}:
        return False, "QUOTE_CERTIFICATE_ID_MISSING"
    if certificate.feed in {"", "UNVERIFIED"} or certificate.plan in {"", "UNVERIFIED"}:
        return False, "QUOTE_FEED_OR_PLAN_UNVERIFIED"
    if not certificate.capability_hash or len(certificate.capability_hash) != 64:
        return False, "QUOTE_CAPABILITY_HASH_INVALID"
    if certificate.capability_hash != certificate.computed_capability_hash:
        return False, "QUOTE_CAPABILITY_HASH_INVALID"
    if certificate.valid_from is not None and now < certificate.valid_from:
        return False, "QUOTE_CERTIFICATE_NOT_YET_VALID"
    if certificate.valid_to is not None and now > certificate.valid_to:
        return False, "QUOTE_CERTIFICATE_EXPIRED"
    if certificate.symbol_scope and symbol not in certificate.symbol_scope:
        return False, "QUOTE_CERTIFICATE_SYMBOL_SCOPE_MISMATCH"
    if certificate.currency_scope and quote.currency not in certificate.currency_scope:
        return False, "QUOTE_CERTIFICATE_CURRENCY_SCOPE_MISMATCH"
    if quote.session is ExecutionSession.CLOSED:
        return False, "QUOTE_SESSION_UNSUPPORTED"
    if quote.extended_hours and not certificate.supports_extended_hours:
        return False, "QUOTE_EXTENDED_HOURS_UNSUPPORTED"
    if not quote.is_fresh(now):
        return False, "QUOTE_STALE_OR_FUTURE"
    if quote.spread > max_spread:
        return False, "QUOTE_SPREAD_EXCEEDS_POLICY"
    return True, "PASS"


def build_manual_order_draft(
    *,
    readiness: ManualReadinessCertificate,
    quote: ExecutionQuote,
    capability_certificate: ExecutionQuoteCapabilityCertificate,
    side: Side | str,
    quantity: Decimal,
    now: datetime,
    target_weight: Decimal = Decimal("0"),
    current_weight: Decimal = Decimal("0"),
    target_quantity: Decimal | None = None,
    current_quantity: Decimal = Decimal("0"),
    time_in_force: str = "DAY",
    aggressiveness: Decimal = Decimal("0"),
    tick_size: Decimal = Decimal("0.01"),
    max_spread: Decimal = Decimal("0.02"),
    risk_checks: tuple[str, ...] = (),
    draft_id: str | None = None,
) -> ManualOrderDraft:
    """Create the only production-shaped manual draft path."""
    side = Side(side)
    if not isinstance(readiness, ManualReadinessCertificate):
        raise TypeError("BLOCKED_MANUAL_READINESS_CERTIFICATE_TYPE")
    if readiness.status is not ManualReadinessStatus.READY:
        raise ValueError("BLOCKED_MANUAL_READINESS_CERTIFICATE")
    if not all(readiness.gates.values()):
        raise ValueError("BLOCKED_MANUAL_READINESS_INCOMPLETE_GATES")
    if readiness.execution_quote_certificate_id != capability_certificate.certificate_id:
        raise ValueError("BLOCKED_QUOTE_CERTIFICATE_ID_MISMATCH")
    usable, reason = _certificate_is_usable(
        quote,
        capability_certificate,
        now=now,
        symbol=quote.symbol,
        max_spread=max_spread,
    )
    if not usable:
        raise ValueError(reason)
    if quantity <= 0:
        raise ValueError("BLOCKED_QUANTITY_INVALID")
    limit = ManualLimitPricePolicy.calculate(
        quote, side, aggressiveness=aggressiveness, tick_size=tick_size
    )
    if target_quantity is None:
        target_quantity = quantity
    stable_id = draft_id or hashlib.sha256(
        json.dumps(
            {
                "run_id": readiness.run_id,
                "symbol": quote.symbol,
                "side": side.value,
                "quantity": str(quantity),
                "quote": quote.stable_json(),
                "certificate": readiness.certificate_id,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()[:32]
    return ManualOrderDraft(
        draft_id=f"draft_{stable_id}",
        run_id=readiness.run_id,
        readiness_certificate_id=readiness.certificate_id,
        symbol=quote.symbol,
        side=side,
        quantity=quantity,
        limit_price=limit,
        time_in_force_recommendation=time_in_force,
        quote_id=f"quote_{hashlib.sha256(quote.stable_json().encode()).hexdigest()[:32]}",
        quote_provider=quote.provider,
        quote_timestamp=quote.timestamp,
        quote_certificate_id=capability_certificate.certificate_id,
        target_weight=target_weight,
        current_weight=current_weight,
        target_quantity=target_quantity,
        current_quantity=current_quantity,
        risk_checks=risk_checks,
        created_at=now,
    )


class ManualReadinessAuthority:
    """Named façade used by integrations to prevent alternate transitions."""

    issue = staticmethod(issue_manual_readiness_certificate)
    build_draft = staticmethod(build_manual_order_draft)
