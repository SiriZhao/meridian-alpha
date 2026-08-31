"""Generate the Gate 6E release-candidate audit from safe local artifacts."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from meridian.finrlx_runtime import inspect_finrlx_runtime
from meridian.profiles import RuntimeProfile

ROOT = Path(__file__).parents[1]


def main() -> None:
    reports = ROOT / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    security = reports / "gate4f-security-master.json"
    security_payload = json.loads(security.read_text(encoding="utf-8")) if security.is_file() else {}
    captured = int(security_payload.get("captured", security_payload.get("captured_count", security_payload.get("authoritative_count", 0))))
    authoritative = int(security_payload.get("runtime_authoritative", security_payload.get("authoritative_count", 0)))
    finrlx = inspect_finrlx_runtime()
    matrix = {
        "Account truth": {"IMPLEMENTED": True, "REAL": False, "PIT_CERTIFIED": False, "SHADOW": True, "EXECUTABLE": False, "TESTED": True, "BLOCKER": "real sanitized Host input required"},
        "Security identity": {"IMPLEMENTED": True, "REAL": captured == 11, "PIT_CERTIFIED": False, "SHADOW": True, "EXECUTABLE": False, "TESTED": True, "BLOCKER": "explicit verified artifact load required" if authoritative != 11 else "historical intervals remain bounded"},
        "Market": {"IMPLEMENTED": True, "REAL": True, "PIT_CERTIFIED": False, "SHADOW": True, "EXECUTABLE": False, "TESTED": True, "BLOCKER": "execution-grade provider not certified"},
        "Fundamentals": {"IMPLEMENTED": True, "REAL": True, "PIT_CERTIFIED": True, "SHADOW": True, "EXECUTABLE": False, "TESTED": True, "BLOCKER": "none for covered issuers"},
        "LLM": {"IMPLEMENTED": True, "REAL": True, "PIT_CERTIFIED": True, "SHADOW": True, "EXECUTABLE": False, "TESTED": True, "BLOCKER": "research alpha only"},
        "Dislocation": {"IMPLEMENTED": True, "REAL": False, "PIT_CERTIFIED": True, "SHADOW": True, "EXECUTABLE": False, "TESTED": True, "BLOCKER": "bounded shadow analysis"},
        "Quote": {"IMPLEMENTED": True, "REAL": False, "PIT_CERTIFIED": False, "SHADOW": False, "EXECUTABLE": False, "TESTED": True, "BLOCKER": "TO_BE_SELECTED/certificate absent"},
        "Manual ticket": {"IMPLEMENTED": True, "REAL": False, "PIT_CERTIFIED": False, "SHADOW": True, "EXECUTABLE": False, "TESTED": True, "BLOCKER": "Host and quote gates"},
        "Host": {"IMPLEMENTED": True, "REAL": False, "PIT_CERTIFIED": False, "SHADOW": True, "EXECUTABLE": False, "TESTED": True, "BLOCKER": "no externally authorized envelope"},
        "Replay": {"IMPLEMENTED": True, "REAL": False, "PIT_CERTIFIED": True, "SHADOW": True, "EXECUTABLE": False, "TESTED": True, "BLOCKER": "none"},
        "FinRL-X": {"IMPLEMENTED": True, "REAL": finrlx.runtime_available, "PIT_CERTIFIED": False, "SHADOW": False, "EXECUTABLE": False, "TESTED": True, "BLOCKER": finrlx.status.value},
        "Broker": {"IMPLEMENTED": False, "REAL": False, "PIT_CERTIFIED": False, "SHADOW": False, "EXECUTABLE": False, "TESTED": True, "BLOCKER": "permanent product boundary"},
    }
    report = {
        "schema_version": "gate6e.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "SHADOW",
        "profiles": [profile.value for profile in RuntimeProfile],
        "auto_execution_profile": False,
        "security_capture": captured,
        "security_runtime_authoritative": authoritative,
        "quote_provider": "TO_BE_SELECTED",
        "quote_certified": False,
        "real_host_input": False,
        "manual_entry_ready": False,
        "finrlx": finrlx.model_dump(mode="json"),
        "product_readiness_matrix": matrix,
        "known_p0": 0,
        "known_p1": ["No real Host envelope supplied", "No execution quote certificate", "FinRL-X runtime/artifact unavailable"],
        "known_p2": [],
        "safety": {"broker": "NONE", "schwab": "NOT CONNECTED", "real_orders": 0, "automatic_model_promotion": False},
    }
    (reports / "gate6e-product-readiness.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = ["# Gate 6E product readiness matrix", "", "Status: **SHADOW / NOT AUTHORIZED FOR ENTRY**", "", "| Capability | Implemented | Real | PIT certified | Shadow | Executable | Tested | Blocker |", "| --- | :---: | :---: | :---: | :---: | :---: | :---: | --- |"]
    for name, item in matrix.items():
        lines.append(f"| {name} | {str(item['IMPLEMENTED']).upper()} | {str(item['REAL']).upper()} | {str(item['PIT_CERTIFIED']).upper()} | {str(item['SHADOW']).upper()} | {str(item['EXECUTABLE']).upper()} | {str(item['TESTED']).upper()} | {item['BLOCKER']} |")
    lines.extend(["", "Profiles: `TEST`, `REPLAY`, `SHADOW_LIVE`, `MANUAL_DECISION_SUPPORT`. `AUTO_EXECUTION` is not defined.", "", "No broker writes, real orders, Schwab authentication, or automatic FinRL-X promotion are present."])
    (reports / "gate6e-product-readiness.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "profiles": report["profiles"], "finrlx": finrlx.status.value, "known_p0": 0}, sort_keys=True))


if __name__ == "__main__":
    main()

