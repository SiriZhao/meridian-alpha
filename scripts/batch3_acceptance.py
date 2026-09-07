"""Batch 3 evidence collector: synthetic CLI runs plus read-only public probes.

Requires the separately built/installed wheel in artifacts/batch3/installed-resume.
No real account discovery, credential values, broker calls or policy changes.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    session = ROOT / "artifacts" / "batch3" / ("acceptance-" + uuid4().hex[:10])
    session.mkdir(parents=True)
    outside = Path(tempfile.mkdtemp(prefix="Meridian outside 中文 # "))
    assert not outside.is_relative_to(ROOT)
    runtime = outside / "runtime 中文 # space"
    env = {**os.environ, "MERIDIAN_HOME": str(runtime), "PYTHONUTF8": "1",
           "PYTHONDONTWRITEBYTECODE": "1"}
    # Installed resource discovery must be proven without an inherited override.
    env.pop("MERIDIAN_POLICY_DIR", None)
    installed = ROOT / "artifacts/batch3/installed-resume/Scripts"
    executable = installed / "meridian.exe"
    evidence = {"environment": {"os": platform.platform(), "python": sys.version,
        "branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip(),
        "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()},
        "session": str(session), "runs": [], "account": "BLOCKED_MISSING_REAL_HOST_SNAPSHOT",
        "synthetic_scope": "REGRESSION_ONLY"}

    def invoke(label, command, *, expected=None):
        start = datetime.now(UTC)
        process = subprocess.run([str(part) for part in command], cwd=outside, env=env,
            capture_output=True, text=True, encoding="utf-8", timeout=120, check=False)
        finish = datetime.now(UTC)
        assert "Traceback" not in process.stdout + process.stderr, label
        result = json.loads(process.stdout)
        record = {"label": label, "start": start.isoformat(), "finish": finish.isoformat(),
                  "latency_seconds": (finish-start).total_seconds(), "exit_code": process.returncode,
                  "payload": result}
        evidence["runs"].append(record)
        (session / "attempt-evidence.json").write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
        if expected is not None:
            assert process.returncode == expected, (label, result)
        return result

    origin = subprocess.check_output([str(installed / "python.exe"), "-c",
        "import json,meridian; from meridian.runtime import policy_directory; print(json.dumps({'package':meridian.__file__,'policies':str(policy_directory())}))"],
        cwd=outside, env=env, text=True, encoding="utf-8")
    evidence["installed_resources"] = json.loads(origin)
    assert "installed-resume" in origin and "site-packages" in origin
    invoke("wheel_init", [executable, "init", "--json"], expected=0)
    invoke("wheel_doctor", [executable, "doctor", "--json"], expected=0)
    missing = invoke("wheel_missing_snapshot", [executable, "daily", "--json"], expected=2)
    assert missing["readiness"]["recommendation_readiness"] == "BLOCKED"

    market = outside / "synthetic market.json"
    account = outside / "synthetic account.json"
    for index in range(2):
        now = datetime.now(UTC).isoformat()
        account.write_text(json.dumps({"snapshot_id": f"batch3-synthetic-{index}", "source_kind": "fixture",
            "source_name": "synthetic-acceptance", "as_of": now, "retrieved_at": now,
            "coverage_status": "COMPLETE", "cash": "10000", "total_equity": "10000"}), encoding="utf-8")
        market.write_text(json.dumps({"quotes": [{"ticker": "AAPL", "timestamp": now,
            "last": "100", "bid": "99.9", "ask": "100.1", "previous_close": "99", "volume": 1000000,
            "atr14": "2", "vwap": "100", "daily_return": "0.05", "gap_percent": "0.01",
            "freshness_state": "VERIFIED"}]}), encoding="utf-8")
        args = ["daily", "--snapshot", str(account), "--market-fixture", str(market), "--json"]
        command = [executable, *args] if index == 0 else ["powershell.exe", "-NoProfile",
            "-ExecutionPolicy", "Bypass", "-File", ROOT / "scripts/run_meridian.ps1", *args]
        result = invoke("wheel_daily" if index == 0 else "powershell5_launcher_daily", command, expected=0)
        assert result["data_mode"] == "FIXTURE"
        assert result["readiness"]["recommendation_readiness"] == "BLOCKED"
        assert result["next_actions"]
        for file in result["output_files"].values():
            assert Path(file).is_file() and Path(file).is_relative_to(runtime)
    evidence["powershell_version"] = subprocess.check_output(["powershell.exe", "-NoProfile", "-Command",
        "$PSVersionTable.PSVersion.ToString()"], text=True).strip()
    with closing(sqlite3.connect(runtime / "db/meridian.sqlite3")) as connection:
        evidence["database"] = {"runs": connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0],
            "readiness_records": connection.execute("SELECT COUNT(*) FROM run_readiness").fetchone()[0],
            "integrity": connection.execute("PRAGMA integrity_check").fetchone()[0]}
        assert evidence["database"] == {"runs": 3, "readiness_records": 3, "integrity": "ok"}
    database = runtime / "db/meridian.sqlite3"
    moved = database.with_suffix(".rename-check")
    database.rename(moved)
    moved.rename(database)
    invoke("restart_doctor", [executable, "doctor", "--json"], expected=0)
    invoke("real_public_provider_matrix", [executable, "data-status", "--json"])
    # Presence metadata only; a key is never printed, copied or deemed a probe.
    evidence["live_research"] = {"credential_status": "CONFIGURED_UNPROBED" if bool(os.environ.get("DEEPSEEK_API_KEY")) else "NOT_CONFIGURED",
        "actual_invocation": False, "status": "NOT_RUN", "reason": "Fresh explicit real Host snapshot absent; canonical prerequisites not satisfied."}
    wheel = ROOT / "artifacts/batch3/wheel-resume/meridian_alpha-0.0.0-py3-none-any.whl"
    evidence["wheel_sha256"] = hashlib.sha256(wheel.read_bytes()).hexdigest()
    destination = ROOT / "docs/evidence/batch3/runtime-resume.json"
    destination.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"evidence": str(destination), "session": str(session), "runs": len(evidence["runs"])}))


if __name__ == "__main__":
    main()
