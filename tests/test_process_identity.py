"""Deterministic Linux exit-race injection, also exercised on Windows CI."""
from __future__ import annotations

import errno
from pathlib import Path

import pytest

import meridian.runtime_io as runtime_io


@pytest.mark.parametrize("state", ["Z", "X", "x", "R", "S", "D", "T", "I"])
def test_linux_process_liveness_includes_retained_exited_stat(monkeypatch: pytest.MonkeyPatch, state: str) -> None:
    monkeypatch.setattr(runtime_io.sys, "platform", "linux")
    fields = [state, *(["0"] * 18), "30809"]
    monkeypatch.setattr(Path, "read_text", lambda self: "12345 (command with ) in name) " + " ".join(fields))
    result = runtime_io.process_start_time(12345)
    assert result == (None if state in {"Z", "X", "x"} else "30809")


@pytest.mark.parametrize("stat", ["", "12345 (command) R 0", "12345 (command) R " + "0 " * 18 + "unknown"])
def test_malformed_linux_identity_is_never_treated_as_exit(monkeypatch: pytest.MonkeyPatch, stat: str) -> None:
    monkeypatch.setattr(runtime_io.sys, "platform", "linux")
    monkeypatch.setattr(Path, "read_text", lambda self: stat)
    with pytest.raises(OSError, match="PROCESS_IDENTITY_UNVERIFIABLE"):
        runtime_io.process_start_time(12345)

@pytest.mark.parametrize("failure", [FileNotFoundError(errno.ENOENT, "gone"), ProcessLookupError(errno.ESRCH, "exited while reading")])
def test_process_exit_during_stat_read_is_not_alive(monkeypatch: pytest.MonkeyPatch, failure: OSError) -> None:
    monkeypatch.setattr(runtime_io.sys, "platform", "linux")

    def read_stat(self: Path, *args: object, **kwargs: object) -> str:
        assert str(self).replace("\\", "/") == "/proc/12345/stat"
        raise failure

    monkeypatch.setattr(Path, "read_text", read_stat)
    assert runtime_io.process_start_time(12345) is None


@pytest.mark.parametrize("failure", [PermissionError(errno.EACCES, "denied"), OSError(errno.EIO, "unverifiable")])
def test_unverifiable_process_identity_still_fails_closed(monkeypatch: pytest.MonkeyPatch, failure: OSError) -> None:
    monkeypatch.setattr(runtime_io.sys, "platform", "linux")

    def read_stat(self: Path, *args: object, **kwargs: object) -> str:
        raise failure

    monkeypatch.setattr(Path, "read_text", read_stat)
    with pytest.raises(OSError) as caught:
        runtime_io.process_start_time(12345)
    assert caught.value is failure
