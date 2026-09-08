"""Bounded cache diagnostics for Meridian runtime startup."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from uuid import uuid4


class CacheHealthStatus(StrEnum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class CacheHealth:
    status: CacheHealthStatus
    path: str
    readable: bool
    writable: bool
    atomic_replace: bool
    encrypted: bool
    stale_temporary_files: int
    error_code: str | None
    next_action: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def check_cache_health(path: Path) -> CacheHealth:
    """Probe cache I/O without changing its configured root or exposing content."""
    readable = writable = atomic_replace = False
    encrypted = False
    stale_count = 0
    error_code: str | None = None
    probe = destination = None
    try:
        path.mkdir(parents=True, exist_ok=True)
        readable = path.is_dir()
        try:
            attributes = getattr(path.stat(), "st_file_attributes", 0)
            encrypted = bool(attributes & 0x4000)  # FILE_ATTRIBUTE_ENCRYPTED
        except OSError:
            pass
        try:
            stale_count = sum(
                1
                for item in path.iterdir()
                if item.is_file() and item.suffix.lower() in {".tmp", ".lock"}
            )
        except OSError:
            readable = False
        token = uuid4().hex
        probe = path / f"cache-health-{token}.tmp"
        destination = path / f"cache-health-{token}.json"
        content = b'{"cache_health":"probe"}'
        with probe.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        writable = True
        probe.replace(destination)
        atomic_replace = destination.read_bytes() == content
        if not atomic_replace:
            error_code = "CACHE_READBACK_MISMATCH"
    except OSError:
        error_code = "CACHE_ATOMIC_IO_FAILED"
    finally:
        for item in (probe, destination):
            if item is not None:
                try:
                    item.unlink(missing_ok=True)
                except OSError:
                    error_code = error_code or "CACHE_CLEANUP_FAILED"
    if error_code is not None or not (readable and writable and atomic_replace):
        status = CacheHealthStatus.BLOCKED
        next_action = "Repair the configured cache ACL/EFS access; Meridian will continue without cache writes and block trading when no fresh provider succeeds."
    elif encrypted or stale_count:
        status = CacheHealthStatus.DEGRADED
        next_action = "Review EFS ownership and remove stale cache .tmp/.lock files under the configured RuntimePaths cache."
    else:
        status = CacheHealthStatus.READY
        next_action = "No cache action required."
    return CacheHealth(
        status=status,
        path=str(path),
        readable=readable,
        writable=writable,
        atomic_replace=atomic_replace,
        encrypted=encrypted,
        stale_temporary_files=stale_count,
        error_code=error_code,
        next_action=next_action,
    )