"""Bounded live primary-source identity capture for Gate 4F.

The script is intentionally report-only.  It creates an in-memory promoted
registry from exact response bytes and never changes the development fixture
registry or stores source payloads.  A failed request is an explicit blocker.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import Request, urlopen

from meridian.identity_certification import (
    IdentityCertificationRequest,
    IdentitySourceKind,
    SecurityMasterPromotionService,
    authoritative_count,
)
from meridian.security_master import AssetType, SecurityMaster

EQUITIES = {
    "AAPL": "0000320193",
    "MSFT": "0000789019",
    "NVDA": "0001045810",
    "META": "0001326801",
    "GOOGL": "0001652044",
}
ETF_SOURCES = {
    "SPY": ("SPDR S&P 500 ETF Trust", "https://www.ssga.com/us/en/individual/etfs/funds/spdr-sp-500-etf-trust-spy", "NYSEARCA"),
    "QQQ": ("Invesco QQQ Trust", "https://www.invesco.com/qqq-etf/en/about.html", "NASDAQ"),
    "SGOV": ("iShares 0-3 Month Treasury Bond ETF", "https://www.ishares.com/us/products/314116/ishares-0-3-month-treasury-bond-etf", "NYSEARCA"),
    "GLD": ("SPDR Gold Shares", "https://www.ssga.com/us/en/individual/etfs/funds/spdr-gold-shares-gld", "NYSEARCA"),
    "TLT": ("iShares 20+ Year Treasury Bond ETF", "https://www.ishares.com/us/products/239454/ishares-20-year-treasury-bond-etf", "NASDAQ"),
}
VIX_SOURCE = ("Cboe Volatility Index", "https://www.cboe.com/tradable_products/vix/", "CBOE")


def _fetch(uri: str, *, timeout: float = 8.0) -> tuple[bytes, datetime]:
    request = Request(uri, headers={"User-Agent": "MeridianAlpha/0.1 research; contact unavailable"})
    response = urlopen(request, timeout=timeout)
    payload = response.read()
    return payload, datetime.now(UTC)


def _base_result(symbol: str) -> dict[str, object]:
    return {"ticker": symbol, "status": "UNVERIFIED", "blockers": []}


def _content_mentions(payload: bytes, *terms: str) -> bool:
    text = payload.decode("utf-8", errors="ignore").lower()
    return any(term.lower() in text for term in terms if term)


def run(output_json: Path | None = None, output_markdown: Path | None = None) -> dict[str, object]:
    master = SecurityMaster()
    service = SecurityMasterPromotionService()
    records: list[dict[str, object]] = []
    for symbol, cik in EQUITIES.items():
        result = _base_result(symbol)
        uri = f"https://data.sec.gov/submissions/CIK{cik}.json"
        try:
            payload, retrieved = _fetch(uri)
            data = json.loads(payload.decode("utf-8"))
            reported_cik = str(data.get("cik", "")).zfill(10)
            name = str(data.get("name", "")).strip()
            if reported_cik != cik:
                result["blockers"] = ["IDENTITY_CIK_MISMATCH"]
            elif not name:
                result["blockers"] = ["IDENTITY_LEGAL_NAME_MISSING"]
            else:
                request = IdentityCertificationRequest(
                    canonical_symbol=symbol,
                    legal_name=name,
                    asset_type=AssetType.EQUITY,
                    source_kind=IdentitySourceKind.SEC,
                    source_name="SEC submissions company metadata",
                    source_uri=uri,
                    source_hash=hashlib.sha256(payload).hexdigest(),
                    source_content_hash=hashlib.sha256(payload).hexdigest(),
                    retrieved_at=retrieved,
                    certified_at=retrieved,
                    effective_from=retrieved,
                    exchange="NASDAQ",
                    currency="USD",
                    cik=cik,
                )
                promoted = service.promote_into(master, request)
                result.update({"status": promoted.status.value, "legal_name": name, "cik": cik, "source_uri": uri, "source_hash": request.source_hash, "retrieved_at": retrieved.isoformat(), "blockers": list(promoted.blockers), "identity": promoted.record.model_dump(mode="json") if promoted.record else None})
        except Exception as error:  # noqa: BLE001 - isolate each bounded source
            result["blockers"] = [f"PRIMARY_SOURCE_FETCH_FAILED:{type(error).__name__}"]
        records.append(result)

    for symbol, (name, uri, exchange) in ETF_SOURCES.items():
        result = _base_result(symbol)
        try:
            payload, retrieved = _fetch(uri)
            request = IdentityCertificationRequest(
                canonical_symbol=symbol,
                legal_name=name,
                asset_type=AssetType.ETF,
                source_kind=IdentitySourceKind.ETF_SPONSOR,
                source_name=f"{name} official sponsor",
                source_uri=uri,
                source_hash=hashlib.sha256(payload).hexdigest(),
                source_content_hash=hashlib.sha256(payload).hexdigest(),
                retrieved_at=retrieved,
                certified_at=retrieved,
                effective_from=retrieved,
                exchange=exchange,
                currency="USD",
            )
            if not _content_mentions(payload, symbol, name.split()[0]):
                raise ValueError("IDENTITY_SOURCE_CONTENT_IDENTITY_UNCONFIRMED")
            promoted = service.promote_into(master, request)
            result.update({"status": promoted.status.value, "legal_name": name, "source_uri": uri, "source_hash": request.source_hash, "retrieved_at": retrieved.isoformat(), "blockers": list(promoted.blockers), "identity": promoted.record.model_dump(mode="json") if promoted.record else None})
        except Exception as error:  # noqa: BLE001 - isolate each bounded source
            result["blockers"] = [f"PRIMARY_SOURCE_FETCH_FAILED:{type(error).__name__}"]
        records.append(result)

    symbol = "VIX"
    name, uri, exchange = VIX_SOURCE
    result = _base_result(symbol)
    try:
        payload, retrieved = _fetch(uri)
        request = IdentityCertificationRequest(
            canonical_symbol=symbol,
            legal_name=name,
            asset_type=AssetType.INDEX,
            source_kind=IdentitySourceKind.CBOE,
            source_name="Cboe official VIX documentation",
            source_uri=uri,
            source_hash=hashlib.sha256(payload).hexdigest(),
            source_content_hash=hashlib.sha256(payload).hexdigest(),
            retrieved_at=retrieved,
            certified_at=retrieved,
            effective_from=retrieved,
            exchange=exchange,
            currency="USD",
        )
        if not _content_mentions(payload, symbol, "Cboe", "Volatility Index"):
            raise ValueError("IDENTITY_SOURCE_CONTENT_IDENTITY_UNCONFIRMED")
        promoted = service.promote_into(master, request)
        result.update({"status": promoted.status.value, "legal_name": name, "source_uri": uri, "source_hash": request.source_hash, "retrieved_at": retrieved.isoformat(), "blockers": list(promoted.blockers), "identity": promoted.record.model_dump(mode="json") if promoted.record else None})
    except Exception as error:  # noqa: BLE001 - isolate each bounded source
        result["blockers"] = [f"PRIMARY_SOURCE_FETCH_FAILED:{type(error).__name__}"]
    records.append(result)

    report: dict[str, object] = {
        "schema_version": "1",
        "gate": "4F",
        "created_at": datetime.now(UTC).isoformat(),
        "bounded_universe": list(EQUITIES) + list(ETF_SOURCES) + ["VIX"],
        "authoritative_count": authoritative_count(master),
        "records": records,
        "development_fixture_authoritative_count": SecurityMaster().authoritative_count(),
        "historical_identity_posture": "current-source interval only; earlier intervals remain blocked unless separately evidenced",
    }
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if output_markdown is not None:
        output_markdown.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# Gate 4F Security Master provenance",
            "",
            f"Authoritative primary-source records: **{report['authoritative_count']}/11**",
            "",
            "| Ticker | Status | Source | Blockers |",
            "| --- | --- | --- | --- |",
        ]
        for item in records:
            lines.append(f"| {item['ticker']} | {item['status']} | {item.get('source_uri', 'not retrieved')} | {', '.join(item.get('blockers', [])) or '—'} |")
        lines.extend(["", "Identity certification is separate from Yahoo/provider symbol mappings. Historical replay before the captured interval remains blocked."])
        output_markdown.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    root = Path(__file__).parents[1]
    report = run(root / "reports" / "gate4f-security-master.json", root / "reports" / "gate4f-security-master.md")
    print(json.dumps({"authoritative_count": report["authoritative_count"], "records": len(report["records"])}))
