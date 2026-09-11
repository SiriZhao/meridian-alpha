"""Provider protocol and sanitized failure boundary."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from meridian.data.models import EvidenceRecord, ResearchDataRequirement


class RetrievalProviderError(RuntimeError):
    def __init__(self, code: str, *, retryable: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


class RetrievalProvider(Protocol):
    provider_name: str

    def supports(self, requirement: ResearchDataRequirement) -> bool: ...

    def retrieve(
        self, requirement: ResearchDataRequirement, *, as_of: datetime
    ) -> tuple[EvidenceRecord, ...]: ...
