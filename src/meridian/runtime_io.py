"""Fail-closed filesystem primitives and process-lifetime run isolation."""
from __future__ import annotations

import ctypes
import json
import os
import socket
import sys
import tempfile
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


def filesystem_detail(error: OSError, operation: str, path: Path) -> dict[str, object]:
    from meridian.runtime import RuntimePaths
    try:
        runtime_home = str(RuntimePaths.from_environment().home)
    except RuntimeError:
        runtime_home = os.environ.get('MERIDIAN_HOME', 'UNRESOLVED')
    return {
        "operation": operation, "absolute_path": str(path.absolute()),
        "exception_type": type(error).__name__, "WinError": getattr(error, "winerror", None),
        "errno": error.errno, "process_id": os.getpid(),
        "MERIDIAN_HOME": runtime_home,
        "cwd": str(Path.cwd()),
    }


class FilesystemFailure(OSError):
    def __init__(self, error: OSError, operation: str, path: Path):
        self.detail = filesystem_detail(error, operation, path)
        super().__init__(error.errno, json.dumps(self.detail), str(path.absolute()))


def _cleanup(paths: tuple[Path, ...], primary: FilesystemFailure | None) -> None:
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError as error:
            if primary is None:
                raise FilesystemFailure(error, 'CLEANUP_DELETE', path) from error
            # Preserve the original failure while exposing cleanup failure as well.
            primary.detail['cleanup_failure'] = filesystem_detail(error, 'CLEANUP_DELETE', path)
            primary.add_note(json.dumps(primary.detail['cleanup_failure']))


def atomic_write(path: Path, content: str | bytes) -> None:
    """Same-directory exclusive staging; never downgrade an atomicity failure."""
    temporary = path.parent / ("." + path.name + "." + uuid4().hex + ".tmp")
    operation = "CREATE"
    failure: FilesystemFailure | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open("xb") as handle:
            operation = "WRITE"
            handle.write(content.encode("utf-8") if isinstance(content, str) else content)
            operation = "FLUSH"
            handle.flush()
            os.fsync(handle.fileno())
            operation = "CLOSE"
        operation = "ATOMIC_REPLACE"
        os.replace(temporary, path)
    except OSError as error:
        failure = FilesystemFailure(error, operation, path)
        raise failure from error
    finally:
        _cleanup((temporary,), failure)


def write_probe(directory: Path) -> None:
    path = directory / ("fs_probe_" + uuid4().hex)
    renamed = path.with_suffix(".renamed")
    operation = "CREATE"
    failure: FilesystemFailure | None = None
    try:
        with path.open("xb") as handle:
            operation = "WRITE"
            handle.write(b"meridian-fs-probe")
            operation = "FLUSH"
            handle.flush()
            os.fsync(handle.fileno())
            operation = "CLOSE"
        operation = "READ"
        if path.read_bytes() != b"meridian-fs-probe":
            raise OSError("Probe readback mismatch")
        operation = "ATOMIC_RENAME"
        os.replace(path, renamed)
        # Also test replacement of an existing destination.
        operation = "CREATE_REPLACEMENT"
        with path.open("xb") as handle:
            operation = "WRITE_REPLACEMENT"
            handle.write(b"replacement")
            operation = "FLUSH_REPLACEMENT"
            handle.flush()
            os.fsync(handle.fileno())
            operation = "CLOSE_REPLACEMENT"
        operation = "ATOMIC_REPLACE"
        os.replace(path, renamed)
        operation = "READ_REPLACEMENT"
        if renamed.read_bytes() != b"replacement":
            raise OSError('Replacement readback mismatch')
        operation = "DELETE"
        renamed.unlink()
    except OSError as error:
        failure = FilesystemFailure(error, operation, path)
        raise failure from error
    finally:
        _cleanup((path, renamed), failure)


def process_start_time(pid: int) -> str | None:
    if sys.platform == "win32":
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            if ctypes.get_last_error() == 87:
                return None
            raise OSError(ctypes.get_last_error(), "PROCESS_IDENTITY_UNVERIFIABLE")
        try:
            exit_code = wintypes.DWORD()
            if not kernel.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                raise OSError(ctypes.get_last_error(), "PROCESS_LIVENESS_UNVERIFIABLE")
            if exit_code.value != 259:  # STILL_ACTIVE; a terminated process can retain a PID handle.
                return None
            times = [wintypes.FILETIME() for _ in range(4)]
            if not kernel.GetProcessTimes(handle, *(ctypes.byref(item) for item in times)):
                raise OSError(ctypes.get_last_error(), "PROCESS_TIME_UNVERIFIABLE")
            return str((times[0].dwHighDateTime << 32) | times[0].dwLowDateTime)
        finally:
            kernel.CloseHandle(handle)
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
    except FileNotFoundError:
        return None


@contextmanager
def run_lock(directory: Path, run_id: str, name: str = "production"):
    """A persistent OS guard prevents stale-metadata cleanup/acquisition races."""
    directory.mkdir(parents=True, exist_ok=True)
    guard = directory / (name + ".guard")
    metadata = directory / (name + ".lock")
    with guard.open("a+b") as handle:
        if guard.stat().st_size == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise FilesystemFailure(error, "LOCK_ACTIVE_DUPLICATE_PROCESS", metadata) from error
        try:
            if metadata.exists():
                try:
                    previous = json.loads(metadata.read_text(encoding="utf-8"))
                    if not isinstance(previous, dict) or not {"hostname", "pid", "process_start_time"} <= previous.keys():
                        raise ValueError("invalid lock metadata")
                    previous_pid = int(previous["pid"])
                except (ValueError, TypeError) as error:
                    raise OSError("LOCK_METADATA_CORRUPT: preserve metadata and inspect ownership") from error
                if previous["hostname"] != socket.gethostname():
                    raise OSError("LOCK_HOST_IDENTITY_MISMATCH")
                actual = process_start_time(previous_pid)
                if actual is not None and actual == previous["process_start_time"]:
                    raise OSError("LOCK_ACTIVE_DUPLICATE_PROCESS")
                metadata.unlink()
            atomic_write(metadata, json.dumps({
                "pid": os.getpid(), "process_start_time": process_start_time(os.getpid()),
                "created_at": datetime.now(UTC).isoformat(), "run_id": run_id,
                "hostname": socket.gethostname(),
            }))
            try:
                yield
            finally:
                metadata.unlink()
        finally:
            handle.seek(0)
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def research_temporary_directory():
    from meridian.runtime import RuntimePaths
    paths = RuntimePaths.from_environment()
    paths.tmp.mkdir(parents=True, exist_ok=True)
    # Every invocation has an exclusive directory; cleanup occurs after child exit.
    with tempfile.TemporaryDirectory(prefix=uuid4().hex + "-", dir=paths.tmp) as directory:
        yield directory
