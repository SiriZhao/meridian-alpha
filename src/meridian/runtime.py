"""Runtime locations and packaged-resource discovery.

Mutable state is deliberately kept outside the installed package.  This makes
the application usable from a read-only checkout, wheel, or container layer.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


class RuntimePathError(RuntimeError):
    """A sanitized error identifying a runtime filesystem failure."""


@dataclass(frozen=True)
class RuntimePaths:
    """The only supported writable directory layout for Meridian."""

    home: Path
    cache_root: Path | None = None

    @classmethod
    def from_environment(
        cls, environ: Mapping[str, str] | None = None, *, platform: str | None = None
    ) -> RuntimePaths:
        environment = os.environ if environ is None else environ
        override = environment.get("MERIDIAN_HOME")
        # A long-lived desktop host may predate the Windows installation setting.
        # Read only this explicitly named non-secret user variable, never credentials.
        if not override and environ is None and (platform or sys.platform).startswith("win"):
            import winreg
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                    stored, _ = winreg.QueryValueEx(key, "MERIDIAN_HOME")
                    override = str(stored) if stored else None
            except FileNotFoundError:
                pass
        if override:
            home = Path(override).expanduser()
        elif (platform or sys.platform).startswith("win"):
            local_app_data = environment.get("LOCALAPPDATA")
            if not local_app_data:
                if environment.get("MERIDIAN_DEVELOPMENT") == "1":
                    home = Path.cwd() / ".runtime"
                else:
                    raise RuntimePathError("RUNTIME_HOME_UNAVAILABLE:LOCALAPPDATA is not set")
            else:
                home = Path(local_app_data) / "MeridianAlpha"
        else:
            home = Path(environment.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "meridian-alpha"
        cache_override = environment.get("MERIDIAN_CACHE")
        cache_root = Path(cache_override).expanduser() if cache_override else None
        if not home.is_absolute():
            raise RuntimePathError("RUNTIME_HOME_INVALID:MERIDIAN_HOME must be absolute")
        if cache_root is not None and not cache_root.is_absolute():
            raise RuntimePathError("RUNTIME_CACHE_INVALID:MERIDIAN_CACHE must be absolute")
        return cls(home=home, cache_root=cache_root)

    @property
    def tmp(self) -> Path:
        return self.home / "tmp"

    @property
    def locks(self) -> Path:
        return self.home / "locks"

    def preflight(self) -> None:
        from meridian.runtime_io import write_probe
        self.ensure_directories()
        for directory in self.directories().values():
            write_probe(directory)

    @property
    def data(self) -> Path:
        return self.home / "data"

    @property
    def db(self) -> Path:
        return self.home / "db" / "meridian.sqlite3"

    @property
    def cache(self) -> Path:
        return self.cache_root or self.home / "cache"

    @property
    def reports(self) -> Path:
        return self.home / "reports"

    @property
    def logs(self) -> Path:
        return self.home / "logs"

    @property
    def runs(self) -> Path:
        return self.home / "runs"

    @property
    def audit(self) -> Path:
        return self.home / "audit"

    @property
    def config(self) -> Path:
        return self.home / "config"

    def directories(self) -> dict[str, Path]:
        return {
            "state": self.home / "state",
            "tmp": self.tmp,
            "locks": self.locks,
            "research": self.home / "research",
            "snapshots": self.home / "snapshots",
            "research_memory": self.data / "research" / "memory",
            "data": self.data,
            "db": self.db.parent,
            "cache": self.cache,
            "reports": self.reports,
            "logs": self.logs,
            "runs": self.runs,
            "audit": self.audit,
            "config": self.config,
        }

    def ensure_directories(self) -> None:
        try:
            for path in self.directories().values():
                path.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            from meridian.runtime_io import FilesystemFailure
            raise FilesystemFailure(error, 'CREATE_DIRECTORY', path) from error

    def as_dict(self) -> dict[str, str]:
        return {"home": str(self.home), **{name: str(path) for name, path in self.directories().items()}}


def project_root() -> Path:
    """Locate development resources without ever using it as writable state."""
    cwd = Path.cwd()
    if (cwd / "policies").is_dir():
        return cwd
    return Path(__file__).resolve().parents[2]


def policy_directory() -> Path:
    override = os.environ.get("MERIDIAN_POLICY_DIR")
    if override:
        return Path(override).expanduser()
    root = Path(__file__).resolve().parents[2]
    if (root / "policies").is_dir():
        return root / "policies"
    return Path(__file__).parent / "policies"
