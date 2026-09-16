"""Prepare/resume Meridian HOST_CODEX handoffs without polling a model."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"


def main() -> int:
    parser = argparse.ArgumentParser(prog="run_today_codex")
    parser.add_argument("command", choices=("prepare", "resume"))
    parser.add_argument("--context", type=Path)
    parser.add_argument("--job", type=Path)
    parser.add_argument("--result", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--account", default="Schwab-Paper")
    args = parser.parse_args()
    if not PYTHON.is_file():
        print("HOST_LLM_REQUIRED: run scripts/bootstrap_windows.ps1 first", file=sys.stderr)
        return 3
    environment = dict(os.environ)
    environment["MERIDIAN_LLM_MODE"] = "HOST_CODEX"
    command = [str(PYTHON), "-m", "meridian", "paper", "run", "--account", args.account, "--json"]
    if args.command == "resume":
        if not args.job or not args.result:
            parser.error("resume requires --job and --result")
        environment["MERIDIAN_HOST_JOB"] = str(args.job)
        environment["MERIDIAN_HOST_RESULT"] = str(args.result)
    completed = subprocess.run(
        command, cwd=ROOT, env=environment, text=True, encoding="utf-8", check=False
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
