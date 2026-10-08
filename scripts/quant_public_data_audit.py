"""Bounded public history coverage audit; no retrospective PIT certification."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from meridian.historical import NasdaqHistoricalProvider, YahooChartHistoricalProvider
from meridian.quant.experiments import isolated_output
from meridian.quant.features import compute_features
from meridian.security_master import DEFAULT_SECURITY_MASTER
from meridian.trading_calendar import session_close


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--symbols", nargs="+", default=["AAPL", "MSFT", "SPY"])
    args = parser.parse_args()
    output = isolated_output(args.output)
    rows = []
    for symbol in args.symbols:
        for cls in (YahooChartHistoricalProvider, NasdaqHistoricalProvider):
            provider = cls(DEFAULT_SECURITY_MASTER, timeout_seconds=8)
            now = datetime.now(UTC)
            try:
                series = provider.get_series(symbol, (now - timedelta(days=1200)).date(), now.date(), as_of=now, live=True)
                receipt = datetime.now(UTC)
                features = compute_features(series, receipt)
                rows.append({"symbol": symbol, "provider": provider.provider_name, "status": "RETRIEVED_UNCERTIFIED",
                             "bars": len(series.bars), "first": str(series.bars[0].session), "last": str(series.bars[-1].session),
                             "source_mode": series.source_mode, "content_hash": hashlib.sha256(series.stable_json().encode()).hexdigest(),
                             "historically_known_at_close_rows": sum(b.available_at <= session_close(b.session) for b in series.bars),
                             "availability": series.bars[0].available_at.isoformat(), "retrieved_at": receipt.isoformat(),
                             "adjustment_basis": series.bars[0].adjustment_status.value,
                             "feature_quality": features.quality_status, "rejection_reasons": list(features.reasons)})
                break
            except (ValueError, OSError, RuntimeError) as error:
                rows.append({"symbol": symbol, "provider": provider.provider_name, "status": "FETCH_FAILED", "error_type": type(error).__name__})
    result = {"status": "INSUFFICIENT_EVIDENCE", "purpose": "PUBLIC_HISTORY_AVAILABILITY_AUDIT_ONLY", "observations": rows,
              "historical_OOS_performance": None, "corporate_action_coverage": "UNVERIFIED",
              "historical_membership": "UNVERIFIED", "financial_alpha_demonstrated": False,
              "canonical_runtime_written": False, "broker_submission": "DISABLED"}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
