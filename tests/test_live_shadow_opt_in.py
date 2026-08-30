from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from meridian.research import (
    LiveResearchShadowOptIn,
    enable_live_research_shadow,
    normalize_certified_shadow,
)


class Settings:
    live_enabled = False

    def model_copy(self, *, update: dict[str, object]):
        return SimpleNamespace(live_enabled=update["live_enabled"])


def test_live_shadow_requires_explicit_opt_in_and_does_not_mutate_defaults() -> None:
    settings = Settings()
    with pytest.raises(ValueError, match="OPT_IN_REQUIRED"):
        enable_live_research_shadow(settings, LiveResearchShadowOptIn())
    runtime = enable_live_research_shadow(settings, LiveResearchShadowOptIn(enabled=True))
    assert settings.live_enabled is False
    assert runtime.live_enabled is True


def test_live_shadow_rejects_raw_packet_or_context() -> None:
    with pytest.raises(TypeError, match="CertifiedEvidenceView"):
        normalize_certified_shadow(None, None, object(), datetime(2026, 8, 30, tzinfo=UTC))  # type: ignore[arg-type]