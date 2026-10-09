"""Canonical ``meridian`` command, delegating exclusively to ApplicationService."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from meridian.application import MeridianApplicationService
from meridian.canonical_run import cli_summary
from meridian.host_readiness import ReadinessStatus, RecommendationReadiness
from meridian.runtime import RuntimePathError
from meridian.runtime_io import filesystem_detail


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "terminal":
        from meridian.terminal_cli import main as terminal_main
        return terminal_main(sys.argv[2:])
    if len(sys.argv) > 1 and sys.argv[1] == "quant":
        from meridian.quant.cli import main as quant_main
        return quant_main(sys.argv[2:])
    parser = argparse.ArgumentParser(prog="meridian")
    parser.add_argument("command", choices=("version", "paths", "doctor", "init", "data-status", "snapshot", "daily", "dip-scout", "forward-status", "paper", "shadow-run", "live-advisory", "live-readiness", "host-llm", "quant"))
    parser.add_argument("subcommand", nargs="?")
    parser.add_argument("file", nargs="?")
    parser.add_argument("--snapshot")
    parser.add_argument("--role-timeout", type=int, default=90)
    parser.add_argument("--reasoning-effort", choices=("low", "medium", "high"))
    parser.add_argument("--quant-engine", choices=("V2.2_SHADOW", "V2.3_SHADOW"), default="V2.3_SHADOW")
    parser.add_argument("--market-fixture")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--account", default="Schwab-Paper")
    parser.add_argument("--cash")
    parser.add_argument("--currency", default="USD")
    parser.add_argument("--confirm-reset")
    parser.add_argument("--run-id")
    parser.add_argument(
        "--run-purpose",
        choices=("OPERATIONAL_DAILY", "OPERATIONAL_PAPER_DAILY", "ACCEPTANCE_VALIDATION"),
    )
    args = parser.parse_args()
    service = None
    payload: dict[str, object]
    try:
        service = MeridianApplicationService()
        if args.command == "version":
            payload = service.version()
        elif args.command == "paths":
            payload = dict(service.paths_status())
        elif args.command == "doctor":
            payload = service.doctor()
        elif args.command == "init":
            payload = service.init()
        elif args.command == "data-status":
            payload = service.data_status()
        elif args.command == "forward-status":
            payload = service.forward_status()
        elif args.command == "snapshot" and args.subcommand == "validate" and args.file:
            payload = service.snapshot_validate(Path(args.file))
        elif args.command == "live-readiness":
            from meridian.live_readiness import run_readiness
            payload = run_readiness(service.paths)
            payload['status'] = 'DEGRADED' if payload['conclusion'] != 'NO_GO' else 'FAILED'
        elif args.command == "live-advisory":
            from meridian.live_advisory import LiveAdvisoryService
            payload = LiveAdvisoryService(service.paths, quant_engine=args.quant_engine).run(account_name=args.account,
                snapshot_path=Path(args.snapshot) if args.snapshot else None, role_timeout=args.role_timeout,
                reasoning_effort=args.reasoning_effort)
            payload["status"] = "PASS" if payload["LIVE_RUN_READY"] else "DEGRADED" if payload.get('research_workflow_available') else "FAILED"
        elif args.command == "host-llm" and args.subcommand == "prepare":
            from meridian.host_llm import HostJobStage, create_job, machine_handoff
            run_id = args.run_id or f"host-{uuid4().hex}"
            context = json.loads(Path(args.file).read_text(encoding="utf-8")) if args.file else {}
            job, path = create_job(service.paths, run_id=run_id, stage=HostJobStage.RESEARCH,
                market_context=context.get("market_context", {}), portfolio_context=context.get("portfolio_context"),
                risk_context=context.get("risk_context", {}), strategy_context=context.get("strategy_context", {}),
                research_questions=tuple(context.get("research_questions", ())),
                required_output_schema=context.get("required_output_schema", {}))
            payload = {"status": "WAITING_FOR_HOST", **machine_handoff(run_id=run_id, job_path=path,
                next_action="Codex host writes result; resume with host-llm accept --file JOB|RESULT.")}
        elif args.command == "host-llm" and args.subcommand == "accept" and args.file:
            from meridian.host_llm import accept_result, load_job
            job_path, result_path = (Path(item) for item in args.file.split("|", 1))
            job = load_job(job_path)
            result, accepted = accept_result(job, result_path)
            payload = {"status": "PASS", "run_id": job.run_id, "job_id": job.job_id,
                "stage": job.stage.value, "result_path": str(accepted),
                "result": result.model_dump(mode="json"), "execution_authority": "NONE",
                "auto_execution": False, "manual_confirmation_required": True}

        elif args.command == "daily":
            payload = service.daily(
                Path(args.snapshot) if args.snapshot else None,
                Path(args.market_fixture) if args.market_fixture else None,
                run_purpose=args.run_purpose or "OPERATIONAL_DAILY",
            )
        elif args.command == "shadow-run" and args.market_fixture:
            payload = service.shadow_run(Path(args.market_fixture))
        elif args.command == "paper" and args.subcommand == "init":
            payload = service.paper_init(
                args.account,
                cash=Decimal(args.cash) if args.cash is not None else Decimal("100000.00"),
                currency=args.currency,
            )
        elif args.command == "paper" and args.subcommand == "run":
            payload = service.paper_run(
                args.account,
                run_purpose=args.run_purpose or "OPERATIONAL_PAPER_DAILY",
            )
        elif args.command == "paper" and args.subcommand == "status":
            payload = service.paper_status(args.account)
        elif args.command == "paper" and args.subcommand == "history":
            payload = service.paper_history(args.account)
        elif args.command == "paper" and args.subcommand == "trades":
            payload = service.paper_trades(args.account)
        elif args.command == "paper" and args.subcommand == "reset":
            payload = service.paper_reset(args.account, confirmation=args.confirm_reset)
        elif args.command == "dip-scout" and args.file:
            payload = service.dip_scout(Path(args.file))
        else:
            raise ValueError("invalid command arguments")
    except (OSError, ValueError, RuntimePathError, sqlite3.Error) as error:
        if isinstance(error, RuntimePathError):
            code, category, message = "MERIDIAN_RUNTIME_UNAVAILABLE", "USER_FIXABLE", str(error)
        elif isinstance(error, OSError):
            code, category, message = "MERIDIAN_FILESYSTEM_ERROR", "USER_FIXABLE", "Check the indicated path, permissions and file locks; choose a writable MERIDIAN_HOME."
        elif isinstance(error, sqlite3.Error):
            code, category, message = "MERIDIAN_DATABASE_ERROR", "USER_FIXABLE", "Run doctor; check database permissions, locks and schema. Preserve the database."
        elif str(error).startswith("HOST_LLM_"):
            code, category, message = str(error), "DATA_QUALITY", "Host LLM job/result contract validation failed; inspect the run artifact."
        elif str(error) == "PAPER_RESET_CONFIRMATION_REQUIRED":
            code, category, message = "PAPER_RESET_CONFIRMATION_REQUIRED", "USER_FIXABLE", "Reset requires --confirm-reset with the exact paper account name; no account state changed."
        else:
            code, category, message = "MERIDIAN_INPUT_INVALID", "DATA_QUALITY", "Canonical input validation failed; inspect validation_error and validate the sanitized account/market inputs."
        payload = {"status": "FAILED", "runtime_status": "FAILED", "error_code": code, "category": category, "message": message, "validation_error": str(error) if code == "MERIDIAN_INPUT_INVALID" else None, "path": str(getattr(error, "filename", None) or ""), "logs_path": str(service.paths.logs) if service else None, "automatic_recovery": "No destructive recovery attempted"}
        if isinstance(error, OSError):
            payload["filesystem"] = getattr(error, "detail", filesystem_detail(error, "APPLICATION_IO", Path(error.filename or ".")))
        payload.update({"run_id": "failed-" + uuid4().hex,
                        "readiness": RecommendationReadiness(runtime_health=ReadinessStatus.FAILED).model_dump(mode="json"),
                        "errors": [code], "next_actions": [message], "output_files": {}})
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 3
    if "canonical_state" in payload:
        payload["summary"] = cli_summary(payload)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True))
    else:
        print("MERIDIAN ALPHA")
        print("Status: " + str(payload.get("status", "PASS")))
        print(json.dumps(payload, ensure_ascii=False, default=str, indent=2, sort_keys=True))
    if payload.get("exit_code") == 3:
        return 3
    status = str(payload.get("status", "PASS"))
    return 0 if status in {"PASS", "INIT_COMPLETE", "INIT_ALREADY_COMPLETE", "NO_ACTION", "NO_CAPITAL", "DRAFT", "PAPER_INITIALIZED", "PAPER_ACCOUNT_ALREADY_EXISTS", "PAPER_ACCOUNT_READY", "PAPER_HISTORY", "PAPER_TRADES", "PAPER_READY", "PAPER_COMPLETE", "PAPER_NO_TRADE", "PAPER_ALREADY_EXECUTED", "PAPER_RESET_COMPLETE"} else 2 if status in {"DEGRADED", "BLOCKED_STALE_ACCOUNT", "BLOCKED_STALE_MARKET", "INSUFFICIENT_FORWARD_EVIDENCE", "PAPER_BLOCKED", "PAPER_WAITING_FOR_MARKET", "PAPER_ACCOUNT_NOT_FOUND"} else 3


if __name__ == "__main__":
    raise SystemExit(main())
