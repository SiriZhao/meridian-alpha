"""Content-bound engine identity, stable across Windows/Linux line endings."""

import hashlib
from pathlib import Path


def _source_hash() -> str:
    directory = Path(__file__).parent
    parts = []
    for name in ("backtest.py", "experiments.py", "features.py", "integration.py", "metrics.py", "policy.py", "portfolio.py", "regime.py", "signals.py", "version.py"):
        parts.append(name + "\n" + (directory / name).read_text(encoding="utf-8").replace("\r\n", "\n"))
    for name in ("allocation.py", "config.py", "orders.py", "reconciliation.py", "risk.py", "schemas.py", "security.py", "trading_calendar.py"):
        parts.append("core/" + name + "\n" + (directory.parent / name).read_text(encoding="utf-8").replace("\r\n", "\n"))
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


# Freeze at import so a running experiment cannot quietly label the next code
# edit as the implementation it just evaluated.
ENGINE_SOURCE_HASH = _source_hash()
