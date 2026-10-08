"""Run the deterministic repository validation used by local and remote agents."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def run_step(label: str, command: list[str], root: Path) -> bool:
    print(f"== {label} ==", flush=True)
    completed = subprocess.run(command, cwd=root, check=False)
    if completed.returncode:
        print(f"{label} FAILED (exit {completed.returncode})", flush=True)
        return False
    print(f"{label} PASS", flush=True)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Meridian Alpha offline validation.")
    parser.add_argument("--skip-tests", action="store_true", help="run static checks and CLI smoke only")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    python = sys.executable
    steps = [
        ("dependency integrity", [python, "-m", "pip", "check"]),
        ("ruff", [python, "-m", "ruff", "check", "."]),
        ("pyright", [python, "-m", "pyright"]),
    ]
    if not args.skip_tests:
        steps.append(("pytest", [python, "-m", "pytest", "-q"]))
    steps.append(("quant contracts and experiment archive", [python, "scripts/validate_quant_artifacts.py"]))
    steps.append(("cli smoke", [python, "-m", "meridian", "--help"]))
    steps.append(("safe paper acceptance", [python, "-O", "scripts/safe_acceptance.py"]))
    return 0 if all(run_step(label, command, root) for label, command in steps) else 1


if __name__ == "__main__":
    raise SystemExit(main())
