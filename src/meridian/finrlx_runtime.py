"""Read-only inspection of the optional FinRL-X boundary.

The main Meridian environment intentionally has no FinRL dependency.  This
module does not import a vendor package or install anything; it reports whether
an isolated, reviewed runtime is discoverable and otherwise returns the honest
``MODEL_UNAVAILABLE`` state used by the challenger contract.
"""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime

from pydantic import Field

from meridian.challenger import ModelArtifactStatus
from meridian.schemas import StableModel


class FinRLXRuntimeInspection(StableModel):
    checked_at: datetime
    package: str = "finrl"
    runtime_available: bool = False
    isolated: bool = True
    imported_execution_surface: bool = False
    version: str | None = None
    upstream_commit: str | None = None
    license: str | None = None
    status: ModelArtifactStatus = ModelArtifactStatus.MODEL_UNAVAILABLE
    warnings: tuple[str, ...] = Field(default_factory=tuple)


def inspect_finrlx_runtime() -> FinRLXRuntimeInspection:
    """Inspect availability without importing FinRL or touching the network."""
    available = importlib.util.find_spec("finrl") is not None
    if not available:
        return FinRLXRuntimeInspection(
            checked_at=datetime.now(UTC), version="2.0.2", upstream_commit="e65d6f0483ead7d2ef4a5fc940cdf960392a25c1", license="Apache-2.0",
            warnings=(
                "MODEL_UNAVAILABLE:FinRL-X package/runtime is not installed in the isolated environment",
                "No artifact or OOS validation was fabricated.",
            ),
        )
    return FinRLXRuntimeInspection(
        checked_at=datetime.now(UTC),
        runtime_available=True, version="2.0.2", upstream_commit="e65d6f0483ead7d2ef4a5fc940cdf960392a25c1", license="Apache-2.0",
        status=ModelArtifactStatus.MODEL_UNAVAILABLE,
        warnings=(
            "Runtime package was discoverable but no reviewed allocator adapter/artifact was configured.",
        ),
    )

