"""Replay the existing sealed synthetic archive; never today's market or account."""
from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

from meridian.quant.backtest import QuantDataset
from meridian.research_terminal import QuantTerminalRequest
from meridian.terminal_service import TerminalPlanner, render_terminal
from meridian.trading_calendar import session_close


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    with zipfile.ZipFile(root / "docs/quant-v2/experiments/synthetic-full-registry.zip") as archive:
        data = QuantDataset.model_validate_json(archive.read("synthetic-dataset.json"))
    cutoff = session_close(data.series[0].bars[279].session)
    request = QuantTerminalRequest(analysis_cutoff=cutoff, symbols=("AAPL", "MSFT", "NVDA"),
        histories=tuple(h.model_copy(update={"bars": h.bars[:280]}) for h in data.series
            if h.canonical_symbol in {"AAPL", "MSFT", "NVDA", "SPY"}), diagnostic=True)
    if args.request:
        print(request.model_dump_json(indent=2))
    else:
        brief = TerminalPlanner().build(request)
        print(brief.model_dump_json(indent=2) if args.json else render_terminal(brief))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
