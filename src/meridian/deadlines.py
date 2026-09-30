"""Monotonic deadline hierarchy used by bounded research work."""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DeadlineBudget:
    """One parent deadline with explicit cleanup margin.

    Children are leases of the same monotonic deadline; they can never extend
    the parent and a lease is rejected when it would consume the cleanup
    margin.
    """

    started: float
    deadline: float
    cleanup_seconds: float = 1.0

    @classmethod
    def start(cls, seconds: float, *, cleanup_seconds: float = 1.0) -> DeadlineBudget:
        if seconds <= cleanup_seconds:
            raise ValueError("DEADLINE_PARENT_TOO_SMALL_FOR_CLEANUP")
        return cls(time.monotonic(), time.monotonic() + seconds, cleanup_seconds)

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, self.deadline - time.monotonic())

    def child(self, requested_seconds: float) -> float:
        """Return a bounded child lease, preserving parent and cleanup margin."""
        if requested_seconds <= 0:
            return 0.0
        return min(requested_seconds, max(0.0, self.remaining_seconds - self.cleanup_seconds))

    def exhausted(self) -> bool:
        return self.remaining_seconds <= self.cleanup_seconds
