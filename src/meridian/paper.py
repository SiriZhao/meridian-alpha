"""Persistent, conservative paper portfolio ledger for the canonical Meridian runtime.

The ledger is an internal PAPER account source.  It is neither a broker connector
nor evidence of an authenticated Schwab account.  It exports a fresh sanitized
Host envelope solely so the existing canonical daily pipeline can validate and
reconcile the paper account through the same deterministic path.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterable, Mapping
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal
from pathlib import Path

import yaml

from meridian.audit import AuditStore
from meridian.config import ExecutionPolicy, RiskPolicy
from meridian.host_account import HostAccountSnapshotEnvelope, HostCoverageStatus, HostPosition
from meridian.schemas import Side

DEFAULT_ACCOUNT = "Schwab-Paper"
DEFAULT_INITIAL_CASH = Decimal("100000.00")


def _amount(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.0001")), "f")


def _decimal(value: object) -> Decimal:
    return Decimal(str(value))


def _utc(value: datetime | None = None) -> datetime:
    result = value or datetime.now(UTC)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("PAPER_TIMEZONE_REQUIRED")
    return result.astimezone(UTC)


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class PaperSettings:
    """Small, explicit paper-only fill assumptions; no execution quote certification."""

    slippage_bps: Decimal = Decimal("5")
    commission_per_order: Decimal = Decimal("1.00")
    benchmark_symbol: str = "SPY"

    @classmethod
    def from_policy_directory(cls, directory: Path) -> PaperSettings:
        path = directory / "paper.yaml"
        if not path.is_file():
            return cls()
        try:
            body = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as error:
            raise ValueError("PAPER_POLICY_INVALID") from error
        if not isinstance(body, dict):
            raise ValueError("PAPER_POLICY_INVALID")
        try:
            slippage = _decimal(body.get("slippage_bps", "5"))
            commission = _decimal(body.get("commission_per_order", "1.00"))
            benchmark = str(body.get("benchmark_symbol", "SPY")).upper()
        except Exception as error:  # Values are policy-owned, but remain fail-closed.
            raise ValueError("PAPER_POLICY_INVALID") from error
        if slippage < 0 or slippage > Decimal("100") or commission < 0 or not benchmark:
            raise ValueError("PAPER_POLICY_INVALID")
        return cls(slippage_bps=slippage, commission_per_order=commission, benchmark_symbol=benchmark)

    @property
    def slippage_fraction(self) -> Decimal:
        return self.slippage_bps / Decimal("10000")


@dataclass(frozen=True)
class PaperPosition:
    ticker: str
    quantity: Decimal
    average_cost: Decimal


@dataclass(frozen=True)
class PaperAccount:
    account_name: str
    currency: str
    starting_cash: Decimal
    cash: Decimal
    realized_pnl: Decimal
    ledger_version: int
    created_at: datetime
    benchmark_symbol: str
    benchmark_inception_price: Decimal | None
    positions: tuple[PaperPosition, ...]

    @property
    def book_market_value(self) -> Decimal:
        return sum((item.quantity * item.average_cost for item in self.positions), Decimal("0"))

    @property
    def book_nav(self) -> Decimal:
        return self.cash + self.book_market_value


@dataclass(frozen=True)
class PaperOrderIntent:
    paper_order_id: str
    ticker: str
    side: Side
    quantity: Decimal
    reference_price: Decimal
    provider: str

    @property
    def reference_notional(self) -> Decimal:
        return self.quantity * self.reference_price


@dataclass(frozen=True)
class PaperFill:
    fill_id: str
    paper_order_id: str
    ticker: str
    side: Side
    quantity: Decimal
    reference_price: Decimal
    fill_price: Decimal
    slippage_bps: Decimal
    fees: Decimal
    provider: str
    filled_at: datetime

    def as_dict(self) -> dict[str, str]:
        return {
            "fill_id": self.fill_id,
            "paper_order_id": self.paper_order_id,
            "ticker": self.ticker,
            "side": self.side.value,
            "quantity": _amount(self.quantity),
            "reference_price": _amount(self.reference_price),
            "fill_price": _amount(self.fill_price),
            "slippage_bps": _amount(self.slippage_bps),
            "fees": _amount(self.fees),
            "provider": self.provider,
            "filled_at": self.filled_at.isoformat(),
            "quote_kind": "PUBLIC_RESEARCH_QUOTE",
            "execution_environment": "PAPER",
        }


class PaperLedger:
    """The one durable paper account source, in the existing AuditStore database."""

    def __init__(self, store: AuditStore, settings: PaperSettings | None = None) -> None:
        self.store = store
        self.settings = settings or PaperSettings()

    def _state(self, connection: sqlite3.Connection, account_name: str) -> PaperAccount | None:
        row = connection.execute(
            "SELECT * FROM paper_accounts WHERE account_name=?", (account_name,)
        ).fetchone()
        if row is None:
            return None
        positions = tuple(
            PaperPosition(row["ticker"], _decimal(row["quantity"]), _decimal(row["average_cost"]))
            for row in connection.execute(
                "SELECT ticker, quantity, average_cost FROM paper_positions "
                "WHERE account_name=? ORDER BY ticker", (account_name,)
            )
        )
        return PaperAccount(
            account_name=row["account_name"],
            currency=row["currency"],
            starting_cash=_decimal(row["starting_cash"]),
            cash=_decimal(row["cash"]),
            realized_pnl=_decimal(row["realized_pnl"]),
            ledger_version=int(row["ledger_version"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            benchmark_symbol=row["benchmark_symbol"],
            benchmark_inception_price=(
                _decimal(row["benchmark_inception_price"])
                if row["benchmark_inception_price"] is not None
                else None
            ),
            positions=positions,
        )

    def state(self, account_name: str = DEFAULT_ACCOUNT) -> PaperAccount | None:
        self.store.migrate()
        with closing(self.store.connect()) as connection:
            return self._state(connection, account_name)

    def initialize(
        self,
        account_name: str = DEFAULT_ACCOUNT,
        *,
        cash: Decimal = DEFAULT_INITIAL_CASH,
        currency: str = "USD",
        now: datetime | None = None,
    ) -> tuple[PaperAccount, bool]:
        if not account_name or len(account_name) > 128 or cash <= 0 or currency != "USD":
            raise ValueError("PAPER_ACCOUNT_INITIALIZATION_INVALID")
        observed = _utc(now)
        self.store.migrate()
        with closing(self.store.connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = self._state(connection, account_name)
            if existing is not None:
                return existing, False
            connection.execute(
                "INSERT INTO paper_accounts(account_name,currency,starting_cash,cash,realized_pnl,"
                "ledger_version,created_at,benchmark_symbol,benchmark_inception_price) "
                "VALUES(?,?,?,?,?,?,?,?,NULL)",
                (
                    account_name,
                    currency,
                    _amount(cash),
                    _amount(cash),
                    _amount(Decimal("0")),
                    0,
                    observed.isoformat(),
                    self.settings.benchmark_symbol,
                ),
            )
            connection.execute(
                "INSERT INTO paper_ledger(account_name,sequence,event_type,run_id,payload_json,created_at) "
                "VALUES(?,?,?,?,?,?)",
                (
                    account_name,
                    0,
                    "INITIALIZED",
                    None,
                    json.dumps({"starting_cash": _amount(cash), "currency": currency}, sort_keys=True),
                    observed.isoformat(),
                ),
            )
            account = self._state(connection, account_name)
            if account is None:
                raise sqlite3.DatabaseError("PAPER_ACCOUNT_INITIALIZATION_FAILED")
            return account, True

    def reset(self, account_name: str, *, confirmation: str, now: datetime | None = None) -> None:
        if confirmation != account_name:
            raise ValueError("PAPER_RESET_CONFIRMATION_REQUIRED")
        _utc(now)
        self.store.migrate()
        with closing(self.store.connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            if self._state(connection, account_name) is None:
                raise ValueError("PAPER_ACCOUNT_NOT_FOUND")
            for table in ("paper_nav_history", "paper_daily_runs", "paper_fills", "paper_positions", "paper_ledger"):
                connection.execute(f"DELETE FROM {table} WHERE account_name=?", (account_name,))
            connection.execute("DELETE FROM paper_accounts WHERE account_name=?", (account_name,))

    def export_snapshot(self, account_name: str = DEFAULT_ACCOUNT, *, observed_at: datetime | None = None) -> HostAccountSnapshotEnvelope:
        observed = _utc(observed_at)
        account = self.state(account_name)
        if account is None:
            raise ValueError("PAPER_ACCOUNT_NOT_FOUND")
        position_rows = tuple(
            HostPosition(
                ticker=item.ticker,
                quantity=item.quantity,
                market_value=(item.quantity * item.average_cost).quantize(Decimal("0.0001")),
                cost_basis=(item.quantity * item.average_cost).quantize(Decimal("0.0001")),
                currency=account.currency,
            )
            for item in account.positions
        )
        state_hash = _hash(
            {
                "account": account.account_name,
                "version": account.ledger_version,
                "cash": _amount(account.cash),
                "positions": [
                    {"ticker": item.ticker, "quantity": _amount(item.quantity), "average_cost": _amount(item.average_cost)}
                    for item in account.positions
                ],
            }
        )
        identifier = _hash(account.account_name)[:12]
        snapshot_id = f"paper-{identifier}-{account.ledger_version}-{observed.strftime('%Y%m%dT%H%M%S%fZ')}"
        return HostAccountSnapshotEnvelope(
            snapshot_id=snapshot_id,
            source_kind="PAPER_LEDGER",
            source_name=account.account_name,
            as_of=observed,
            retrieved_at=observed,
            coverage_status=HostCoverageStatus.COMPLETE,
            base_currency=account.currency,
            cash=account.cash,
            total_equity=account.book_nav,
            positions=position_rows,
            warnings=(
                "PAPER_ACCOUNT",
                f"PAPER_LEDGER_VERSION={account.ledger_version}",
                f"PAPER_LEDGER_STATE_HASH={state_hash}",
                "BOOK_VALUES_MARKED_SEPARATELY_BY_CANONICAL_MARKET_STAGE",
            ),
        )

    def write_snapshot(self, directory: Path, account_name: str = DEFAULT_ACCOUNT, *, observed_at: datetime | None = None) -> Path:
        envelope = self.export_snapshot(account_name, observed_at=observed_at)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{envelope.snapshot_id}.json"
        path.write_text(envelope.model_dump_json(indent=2) + "\n", encoding="utf-8")
        return path

    def _daily_row(self, connection: sqlite3.Connection, account_name: str, trading_date: str) -> sqlite3.Row | None:
        return connection.execute(
            "SELECT * FROM paper_daily_runs WHERE account_name=? AND trading_date=?",
            (account_name, trading_date),
        ).fetchone()

    def daily_execution(self, account_name: str, trading_date: str) -> dict[str, str] | None:
        self.store.migrate()
        with closing(self.store.connect()) as connection:
            row = self._daily_row(connection, account_name, trading_date)
            return dict(row) if row else None

    def build_order_intents(
        self,
        account_name: str,
        *,
        trading_date: str,
        canonical_run_id: str,
        targets: Iterable[Mapping[str, object]],
        quotes: Mapping[str, Mapping[str, object]],
        risk: RiskPolicy,
        execution: ExecutionPolicy,
    ) -> tuple[PaperOrderIntent, ...]:
        account = self.state(account_name)
        if account is None:
            raise ValueError("PAPER_ACCOUNT_NOT_FOUND")
        prices: dict[str, tuple[Decimal, str]] = {}
        for ticker, raw in quotes.items():
            try:
                price = _decimal(raw["last"])
                provider = str(raw.get("provider") or "PUBLIC_PROVIDER")
            except (KeyError, ArithmeticError, ValueError) as error:
                raise ValueError("PAPER_PUBLIC_QUOTE_INVALID") from error
            if price <= 0:
                raise ValueError("PAPER_PUBLIC_QUOTE_INVALID")
            prices[ticker] = (price, provider)
        if any(item.ticker not in prices for item in account.positions):
            raise ValueError("PAPER_MARK_TO_MARKET_QUOTE_MISSING")
        nav = account.cash + sum((item.quantity * prices[item.ticker][0] for item in account.positions), Decimal("0"))
        if nav <= 0:
            return ()
        target_weights: dict[str, Decimal] = {}
        for item in targets:
            ticker = str(item.get("ticker", "")).upper()
            weight = _decimal(item.get("target_weight", "0"))
            if not ticker or weight < 0 or weight > risk.max_position_weight:
                raise ValueError("PAPER_TARGET_INVALID")
            target_weights[ticker] = weight
        current = {item.ticker: item.quantity for item in account.positions}
        max_order = nav * risk.max_single_order_nav_percent
        turnover_left = nav * risk.max_daily_turnover
        intents: list[PaperOrderIntent] = []

        def add(ticker: str, side: Side, quantity: Decimal) -> None:
            nonlocal turnover_left
            if quantity <= 0 or ticker not in prices:
                return
            price, provider = prices[ticker]
            cap_quantity = (min(max_order, turnover_left) / price).quantize(Decimal("1"), rounding=ROUND_DOWN)
            quantity = min(quantity, cap_quantity)
            if quantity <= 0 or quantity * price < execution.minimum_order_notional:
                return
            order_id = "paper-order-" + _hash(
                {"account": account_name, "date": trading_date, "run": canonical_run_id, "ticker": ticker, "side": side.value, "quantity": _amount(quantity)}
            )[:32]
            intents.append(PaperOrderIntent(order_id, ticker, side, quantity, price, provider))
            turnover_left -= quantity * price

        for ticker in sorted(set(current) - set(target_weights)):
            add(ticker, Side.SELL, current[ticker])
        for ticker in sorted(set(current) & set(target_weights)):
            price = prices[ticker][0]
            desired = target_weights[ticker] * nav
            current_value = current[ticker] * price
            if desired < current_value:
                add(ticker, Side.SELL, ((current_value - desired) / price).quantize(Decimal("1"), rounding=ROUND_DOWN))
        minimum_cash = max(nav * risk.min_cash_weight, account.cash * execution.transaction_reserve_percent)
        available_cash = max(Decimal("0"), account.cash - minimum_cash)
        for ticker in sorted(target_weights):
            if ticker not in prices:
                raise ValueError("PAPER_PUBLIC_QUOTE_INVALID")
            price = prices[ticker][0]
            desired = target_weights[ticker] * nav
            current_value = current.get(ticker, Decimal("0")) * price
            if desired <= current_value:
                continue
            worst = price * (Decimal("1") + self.settings.slippage_fraction)
            quantity = min(
                ((desired - current_value) / worst).quantize(Decimal("1"), rounding=ROUND_DOWN),
                ((available_cash - self.settings.commission_per_order) / worst).quantize(Decimal("1"), rounding=ROUND_DOWN),
            )
            before = len(intents)
            add(ticker, Side.BUY, quantity)
            if len(intents) > before:
                added = intents[-1]
                available_cash -= added.reference_notional * (Decimal("1") + self.settings.slippage_fraction) + self.settings.commission_per_order
        return tuple(intents)

    def execute(
        self,
        account_name: str,
        *,
        trading_date: str,
        canonical_run_id: str,
        intents: Iterable[PaperOrderIntent],
        now: datetime | None = None,
    ) -> tuple[str, tuple[PaperFill, ...]]:
        observed = _utc(now)
        planned = tuple(intents)
        intent_hash = _hash([item.__dict__ for item in planned])
        self.store.migrate()
        with closing(self.store.connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            account = self._state(connection, account_name)
            if account is None:
                raise ValueError("PAPER_ACCOUNT_NOT_FOUND")
            if self._daily_row(connection, account_name, trading_date) is not None:
                return "PAPER_ALREADY_EXECUTED", ()
            cash = account.cash
            realized = account.realized_pnl
            positions = {item.ticker: item for item in account.positions}
            version = account.ledger_version
            fills: list[PaperFill] = []
            for intent in planned:
                if intent.quantity <= 0 or intent.reference_price <= 0:
                    raise ValueError("PAPER_ORDER_INVALID")
                fill_price = intent.reference_price * (
                    Decimal("1") + self.settings.slippage_fraction if intent.side is Side.BUY else Decimal("1") - self.settings.slippage_fraction
                )
                fill_price = fill_price.quantize(Decimal("0.0001"))
                fees = self.settings.commission_per_order
                previous = positions.get(intent.ticker, PaperPosition(intent.ticker, Decimal("0"), Decimal("0")))
                if intent.side is Side.BUY:
                    total = intent.quantity * fill_price + fees
                    if total > cash:
                        raise ValueError("PAPER_INSUFFICIENT_CASH")
                    new_quantity = previous.quantity + intent.quantity
                    average = ((previous.quantity * previous.average_cost) + (intent.quantity * fill_price) + fees) / new_quantity
                    cash -= total
                else:
                    if intent.quantity > previous.quantity:
                        raise ValueError("PAPER_LONG_ONLY_OVERSELL")
                    proceeds = intent.quantity * fill_price - fees
                    cash += proceeds
                    realized += proceeds - (intent.quantity * previous.average_cost)
                    new_quantity = previous.quantity - intent.quantity
                    average = previous.average_cost if new_quantity else Decimal("0")
                if new_quantity:
                    positions[intent.ticker] = PaperPosition(intent.ticker, new_quantity, average)
                else:
                    positions.pop(intent.ticker, None)
                version += 1
                fill_id = "paper-fill-" + _hash({"order": intent.paper_order_id, "at": observed.isoformat()})[:32]
                fill = PaperFill(fill_id, intent.paper_order_id, intent.ticker, intent.side, intent.quantity,
                                 intent.reference_price, fill_price, self.settings.slippage_bps, fees,
                                 intent.provider, observed)
                fills.append(fill)
                connection.execute(
                    "INSERT INTO paper_fills(fill_id,account_name,paper_order_id,canonical_run_id,ticker,side,quantity,reference_price,fill_price,slippage_bps,fees,provider,filled_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (fill.fill_id, account_name, fill.paper_order_id, canonical_run_id, fill.ticker, fill.side.value,
                     _amount(fill.quantity), _amount(fill.reference_price), _amount(fill.fill_price),
                     _amount(fill.slippage_bps), _amount(fill.fees), fill.provider, observed.isoformat()),
                )
                connection.execute(
                    "INSERT INTO paper_ledger(account_name,sequence,event_type,run_id,payload_json,created_at) VALUES(?,?,?,?,?,?)",
                    (account_name, version, "PAPER_FILL", canonical_run_id,
                     json.dumps({key: value for key, value in fill.as_dict().items() if key != "fill_id"}, sort_keys=True), observed.isoformat()),
                )
            connection.execute("DELETE FROM paper_positions WHERE account_name=?", (account_name,))
            connection.executemany(
                "INSERT INTO paper_positions(account_name,ticker,quantity,average_cost,updated_at) VALUES(?,?,?,?,?)",
                [(account_name, item.ticker, _amount(item.quantity), _amount(item.average_cost), observed.isoformat()) for item in positions.values()],
            )
            connection.execute(
                "UPDATE paper_accounts SET cash=?, realized_pnl=?, ledger_version=? WHERE account_name=?",
                (_amount(cash), _amount(realized), version, account_name),
            )
            connection.execute(
                "INSERT INTO paper_daily_runs(account_name,trading_date,canonical_run_id,order_intent_hash,execution_status,created_at) VALUES(?,?,?,?,?,?)",
                (account_name, trading_date, canonical_run_id, intent_hash,
                 "PAPER_COMPLETE" if fills else "PAPER_NO_TRADE", observed.isoformat()),
            )
            return ("PAPER_COMPLETE" if fills else "PAPER_NO_TRADE"), tuple(fills)

    def record_nav(
        self,
        account_name: str,
        *,
        trading_date: str,
        canonical_run_id: str,
        quotes: Mapping[str, Mapping[str, object]],
        now: datetime | None = None,
        fills: Iterable[PaperFill] = (),
    ) -> dict[str, object] | None:
        observed = _utc(now)
        supplied_fills = tuple(fills)
        self.store.migrate()
        with closing(self.store.connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            account = self._state(connection, account_name)
            if account is None:
                raise ValueError("PAPER_ACCOUNT_NOT_FOUND")
            prices: dict[str, Decimal] = {}
            for ticker, raw in quotes.items():
                if "last" in raw:
                    prices[ticker] = _decimal(raw["last"])
            if any(item.ticker not in prices or prices[item.ticker] <= 0 for item in account.positions):
                return None
            market_value = sum((item.quantity * prices[item.ticker] for item in account.positions), Decimal("0"))
            nav = account.cash + market_value
            previous = connection.execute(
                "SELECT nav FROM paper_nav_history WHERE account_name=? AND trading_date<>? ORDER BY observed_at DESC LIMIT 1",
                (account_name, trading_date),
            ).fetchone()
            prior_nav = _decimal(previous["nav"]) if previous else None
            daily_return = (nav / prior_nav - Decimal("1")) if prior_nav and prior_nav > 0 else None
            cumulative_return = nav / account.starting_cash - Decimal("1")
            high = connection.execute(
                "SELECT MAX(CAST(nav AS REAL)) AS high FROM paper_nav_history WHERE account_name=?", (account_name,)
            ).fetchone()["high"]
            high_water = max(_decimal(high) if high is not None else nav, nav)
            drawdown = nav / high_water - Decimal("1")
            benchmark_price = prices.get(account.benchmark_symbol)
            inception = account.benchmark_inception_price
            if inception is None and benchmark_price is not None:
                inception = benchmark_price
                connection.execute(
                    "UPDATE paper_accounts SET benchmark_inception_price=? WHERE account_name=?",
                    (_amount(inception), account_name),
                )
            benchmark_return = benchmark_price / inception - Decimal("1") if benchmark_price is not None and inception else None
            existing_day = connection.execute(
                "SELECT turnover, fees, trade_count FROM paper_nav_history WHERE account_name=? AND trading_date=?",
                (account_name, trading_date),
            ).fetchone()
            if supplied_fills:
                turnover = sum((item.quantity * item.reference_price for item in supplied_fills), Decimal("0"))
                fees = sum((item.fees for item in supplied_fills), Decimal("0"))
                trade_count = len(supplied_fills)
            elif existing_day is not None:
                turnover = _decimal(existing_day["turnover"])
                fees = _decimal(existing_day["fees"])
                trade_count = int(existing_day["trade_count"])
            else:
                turnover = Decimal("0")
                fees = Decimal("0")
                trade_count = 0
            connection.execute(
                "INSERT INTO paper_nav_history(account_name,trading_date,run_id,observed_at,cash,market_value,nav,daily_return,cumulative_return,drawdown,turnover,fees,trade_count,benchmark_price,benchmark_cumulative_return) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(account_name,trading_date) DO UPDATE SET run_id=excluded.run_id,observed_at=excluded.observed_at,cash=excluded.cash,market_value=excluded.market_value,nav=excluded.nav,daily_return=excluded.daily_return,cumulative_return=excluded.cumulative_return,drawdown=excluded.drawdown,turnover=excluded.turnover,fees=excluded.fees,trade_count=excluded.trade_count,benchmark_price=excluded.benchmark_price,benchmark_cumulative_return=excluded.benchmark_cumulative_return",
                (account_name, trading_date, canonical_run_id, observed.isoformat(), _amount(account.cash), _amount(market_value),
                 _amount(nav), _amount(daily_return) if daily_return is not None else None, _amount(cumulative_return),
                 _amount(drawdown), _amount(turnover), _amount(fees), trade_count,
                 _amount(benchmark_price) if benchmark_price is not None else None,
                 _amount(benchmark_return) if benchmark_return is not None else None),
            )
            return {
                "trading_date": trading_date,
                "cash": _amount(account.cash),
                "market_value": _amount(market_value),
                "nav": _amount(nav),
                "daily_return": _amount(daily_return) if daily_return is not None else None,
                "cumulative_return": _amount(cumulative_return),
                "drawdown": _amount(drawdown),
                "benchmark_symbol": account.benchmark_symbol,
                "benchmark_cumulative_return": _amount(benchmark_return) if benchmark_return is not None else None,
                "excess_return": _amount(cumulative_return - benchmark_return) if benchmark_return is not None else None,
                "turnover": _amount(turnover),
                "fees": _amount(fees),
                "trade_count": trade_count,
                "dividends": "NOT_IMPLEMENTED",
            }

    def status(self, account_name: str = DEFAULT_ACCOUNT) -> dict[str, object]:
        account = self.state(account_name)
        if account is None:
            return {"found": False, "status": "PAPER_ACCOUNT_NOT_FOUND", "account": account_name}
        self.store.migrate()
        with closing(self.store.connect()) as connection:
            nav = connection.execute(
                "SELECT * FROM paper_nav_history WHERE account_name=? ORDER BY observed_at DESC LIMIT 1", (account_name,)
            ).fetchone()
        latest = dict(nav) if nav else None
        return {
            "found": True,
            "status": "PAPER_ACCOUNT_READY",
            "account": account.account_name,
            "account_environment": "PAPER",
            "account_provenance": "INTERNAL_PAPER_LEDGER",
            "currency": account.currency,
            "inception": account.created_at.isoformat(),
            "starting_capital": _amount(account.starting_cash),
            "cash": _amount(account.cash),
            "realized_pnl": _amount(account.realized_pnl),
            "book_nav": _amount(account.book_nav),
            "positions": [
                {"ticker": item.ticker, "quantity": _amount(item.quantity), "average_cost": _amount(item.average_cost)}
                for item in account.positions
            ],
            "latest_performance": latest,
            "benchmark": account.benchmark_symbol,
            "ledger_version": account.ledger_version,
            "dividends": "NOT_IMPLEMENTED",
            "broker_submission": "DISABLED",
        }

    def history(self, account_name: str = DEFAULT_ACCOUNT, *, limit: int = 20) -> list[dict[str, object]]:
        self.store.migrate()
        with closing(self.store.connect()) as connection:
            return [dict(row) for row in connection.execute(
                "SELECT * FROM paper_nav_history WHERE account_name=? ORDER BY observed_at DESC LIMIT ?", (account_name, max(1, min(limit, 100))),
            )]

    def trades(self, account_name: str = DEFAULT_ACCOUNT, *, limit: int = 50) -> list[dict[str, object]]:
        self.store.migrate()
        with closing(self.store.connect()) as connection:
            return [dict(row) for row in connection.execute(
                "SELECT fill_id,paper_order_id,canonical_run_id,ticker,side,quantity,reference_price,fill_price,slippage_bps,fees,provider,filled_at FROM paper_fills WHERE account_name=? ORDER BY filled_at DESC LIMIT ?",
                (account_name, max(1, min(limit, 200))),
            )]
