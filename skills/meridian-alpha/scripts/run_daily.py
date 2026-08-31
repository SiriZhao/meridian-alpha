"""Portable Skill entrypoint that delegates analysis to the Meridian core.

The wrapper is deliberately thin: it performs capability checks, invokes the
project-owned CLI when an installed runtime/project root is available, and
renders a sanitized mobile report. It never reproduces financial calculations.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    from preflight import evaluate
except ImportError:  # pragma: no cover - supports module execution from package root
    from .preflight import evaluate  # type: ignore[no-redef]


PROFILES = ("TEST", "REPLAY", "SHADOW_LIVE", "MANUAL_DECISION_SUPPORT")


def _project_root(explicit: Path | None) -> Path | None:
    candidates = []
    if explicit is not None:
        candidates.append(explicit)
    env_root = os.environ.get("MERIDIAN_PROJECT_ROOT")
    if env_root:
        candidates.append(Path(env_root))
    candidates.append(Path.cwd())
    for candidate in candidates:
        root = candidate.resolve()
        if (root / "pyproject.toml").is_file() and (root / "src" / "meridian").is_dir():
            return root
    return None


def _mobile_report(status: str, blockers: list[str]) -> str:
    blocker_text = "、".join(blockers) if blockers else "无"
    return "\n".join(
        (
            "【Meridian Alpha】",
            f"状态：{status}",
            "",
            "【账户】",
            "仅使用本次提供的经验证、脱敏账户快照；不从对话历史推断持仓。",
            "",
            "【市场】",
            "由 Meridian 核心核验；运行时不可用时不生成市场结论。",
            "",
            "【Quant】",
            "仅由确定性 Meridian 核心计算；本次未执行时不虚构数值。",
            "",
            "【认证基本面】",
            "仅展示认证 SEC 证据；未加载时明确阻塞。",
            "",
            "【AI研判】",
            "仅使用认证研究或明确的 REPLAY；不把模型文本当作数量或价格。",
            "",
            "【抄底观察】",
            "需要当前认证市场数据和确定性筛选；不可用时不推荐。",
            "",
            "【目标组合】",
            "仅由 Meridian 核心输出；本次未执行时不虚构目标。",
            "",
            "【风险】",
            "风险与对账门禁未通过前，禁止人工下单草稿。",
            "",
            "【阻塞项】",
            blocker_text,
        )
    )


def _print_result(result: dict[str, Any], blockers: list[str]) -> None:
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    print("---REPORT---")
    print(_mobile_report(str(result.get("status", "BLOCKED")), blockers))


def main() -> int:
    parser = argparse.ArgumentParser(description="Portable Meridian Alpha daily wrapper")
    parser.add_argument("--profile", choices=PROFILES, default="TEST")
    parser.add_argument("--date", help="Timezone-aware ISO decision timestamp")
    parser.add_argument("--snapshot", type=Path, help="Path to a sanitized account envelope")
    parser.add_argument("--project-root", type=Path, help="Optional installed Meridian project root")
    args = parser.parse_args()
    snapshot = args.snapshot
    if snapshot is None and args.profile == "TEST":
        snapshot = Path(__file__).resolve().parents[1] / "fixtures" / "test-account.json"
    preflight = evaluate(args.profile, snapshot)
    if preflight["RUNTIME"] != "AVAILABLE":
        _print_result(
            {
                "status": "MERIDIAN_RUNTIME_UNAVAILABLE",
                "profile": args.profile,
                "blockers": ["PYTHON_RUNTIME_OR_MERIDIAN_PACKAGE_MISSING"],
                "preflight": preflight,
                "analysis_executed": False,
            },
            ["MERIDIAN_RUNTIME_UNAVAILABLE", "PYTHON_RUNTIME_OR_MERIDIAN_PACKAGE_MISSING"],
        )
        return 0
    root = _project_root(args.project_root)
    if root is None:
        _print_result(
            {
                "status": "MERIDIAN_RUNTIME_UNAVAILABLE",
                "profile": args.profile,
                "blockers": ["MERIDIAN_PROJECT_ROOT_UNAVAILABLE"],
                "preflight": preflight,
                "analysis_executed": False,
            },
            ["MERIDIAN_PROJECT_ROOT_UNAVAILABLE"],
        )
        return 0
    if snapshot is None or not snapshot.is_file():
        _print_result(
            {
                "status": "BLOCKED_ACCOUNT_INPUT_REQUIRED",
                "profile": args.profile,
                "blockers": ["SANITIZED_ACCOUNT_SNAPSHOT_REQUIRED"],
                "preflight": preflight,
                "analysis_executed": False,
            },
            ["SANITIZED_ACCOUNT_SNAPSHOT_REQUIRED"],
        )
        return 0
    command = [
        sys.executable,
        "-m",
        "meridian.cli",
        "daily",
        "--profile",
        args.profile,
        "--account-fixture",
        str(snapshot.resolve()),
    ]
    if args.date:
        command.extend(("--date", args.date))
    try:
        completed = subprocess.run(
            command,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        completed = None
    if completed is None or completed.returncode != 0:
        _print_result(
            {
                "status": "MERIDIAN_RUNTIME_FAILED",
                "profile": args.profile,
                "blockers": ["MERIDIAN_CORE_INVOCATION_FAILED"],
                "preflight": preflight,
                "analysis_executed": False,
            },
            ["MERIDIAN_CORE_INVOCATION_FAILED"],
        )
        return 0
    try:
        raw = json.loads(completed.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    safe = {
        key: raw[key]
        for key in ("status", "run_id", "artifact_directory", "authorization", "known_p0")
        if key in raw
    }
    safe.update({"profile": args.profile, "preflight": preflight, "analysis_executed": True})
    blockers = [str(item) for item in raw.get("blockers", [])] if isinstance(raw.get("blockers"), list) else []
    if not blockers and str(safe.get("status", "")).startswith("BLOCKED"):
        blockers = ["MERIDIAN_CORE_REPORTED_BLOCKED"]
    _print_result(safe, blockers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
