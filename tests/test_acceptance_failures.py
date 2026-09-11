"""Operator-level negative acceptance; synthetic input, isolated runtime only."""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from test_recommendation_readiness import envelope

from meridian.application import MeridianApplicationService
from meridian.runtime import RuntimePaths


def cli(tmp_path: Path, args: list[str], *, code: str | None = None):
    command = [sys.executable, "-c", code] if code else [sys.executable, "-m", "meridian"]
    run = subprocess.run(command + args, cwd=tmp_path,
        env={**os.environ, "MERIDIAN_HOME": str(tmp_path / "home # 中文"), "PYTHONUTF8": "1"},
        capture_output=True, text=True, encoding="utf-8", timeout=30, check=False)
    assert "Traceback" not in run.stdout + run.stderr
    result = json.loads(run.stdout)
    assert result["run_id"] and "output_files" in result and result["next_actions"]
    return run.returncode, result


@pytest.mark.parametrize("kind", ["missing", "invalid", "stale", "future"])
def test_snapshot_failures_are_operator_results(tmp_path: Path, kind: str):
    path = tmp_path / "snapshot.json"
    now = datetime.now(UTC)
    if kind == "invalid":
        path.write_text("invalid", encoding="utf-8")
    elif kind != "missing":
        envelope(path, now + timedelta(days=1 if kind == "future" else -2))
    exit_code, result = cli(tmp_path, ["daily", "--snapshot", str(path), "--json"])
    assert exit_code == 2
    assert result["runtime_status"] == "PASS"
    assert result["readiness"]["recommendation_readiness"] == "BLOCKED"
    assert result["research_status"] == "NOT_RUN"


def test_problematic_runtime_path_is_structured(tmp_path: Path):
    (tmp_path / "home # 中文").write_text("preserve", encoding="utf-8")
    exit_code, result = cli(tmp_path, ["daily", "--json"])
    assert exit_code == 3 and result["runtime_status"] == "FAILED"
    assert (tmp_path / "home # 中文").read_text(encoding="utf-8") == "preserve"


@pytest.mark.parametrize("kind", ["locked", "newer"])
def test_database_failure_preserves_history(tmp_path: Path, kind: str):
    paths = RuntimePaths(tmp_path / "home # 中文")
    app = MeridianApplicationService(paths)
    prior = app.daily(None)
    with closing(sqlite3.connect(paths.db)) as connection:
        if kind == "newer":
            connection.execute("INSERT INTO schema_migrations VALUES (99)")
            connection.commit()
        else:
            connection.execute("BEGIN EXCLUSIVE")
        exit_code, result = cli(tmp_path, ["daily", "--json"])
        assert exit_code == 3 and result["runtime_status"] == "FAILED"
        connection.rollback()
        assert connection.execute("SELECT COUNT(*) FROM run_readiness WHERE run_id=?", (prior["run_id"],)).fetchone()[0] == 1
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    paths.db.rename(paths.db.with_suffix(".preserved"))


def test_report_write_failure_keeps_original_run_identity(tmp_path: Path):
    code = '''from pathlib import Path
from meridian.application_cli import main
original = Path.write_text
def fail_markdown(self, *args, **kwargs):
    if self.name == "daily.tmp" and self.with_suffix(".json").exists():
        raise PermissionError("simulated report failure")
    return original(self, *args, **kwargs)
Path.write_text = fail_markdown
raise SystemExit(main())
'''
    exit_code, result = cli(tmp_path, ["daily", "--json"], code=code)
    assert exit_code == 3 and result["runtime_status"] == "FAILED"
    assert result["audit_failure_recorded"] is True
    assert result["error_code"] == "MERIDIAN_REPORT_WRITE_FAILED"
    assert "report_json" not in result["output_files"]
    log = Path(result["output_files"]["log"]).read_text(encoding="utf-8")
    assert result["run_id"] in log and "MERIDIAN_REPORT_WRITE_FAILED" in log
    paths = RuntimePaths(tmp_path / "home # 中文")
    with closing(sqlite3.connect(paths.db)) as connection:
        assert connection.execute("SELECT COUNT(*) FROM run_readiness WHERE run_id=?", (result["run_id"],)).fetchone()[0] == 1
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


@pytest.mark.parametrize(("kind", "status"), [
    ("ok", "AVAILABLE"),
    ("missing", "CODEX_NOT_INSTALLED"),
    ("auth", "CODEX_AUTH_REQUIRED"),
    ("timeout", "CODEX_TIMEOUT"),
    ("malformed", "CODEX_SCHEMA_ERROR"),
    ("schema", "CODEX_SCHEMA_ERROR"),
])
def test_canonical_cli_research_faults(tmp_path: Path, kind: str, status: str):
    from test_daily_closure import market
    now = datetime.now(UTC)
    account = envelope(tmp_path / "synthetic.json", now)
    quote_file = tmp_path / "quotes.json"
    quote_file.write_text(json.dumps({"quotes": [q.model_dump(mode="json") for q in market(timestamp=now).values()]}), encoding="utf-8")
    code = """import json
from dataclasses import replace
from pathlib import Path
import meridian.application as app
from meridian.application_cli import main
from meridian.codex_provider import CodexCliProvider, ProcessResult
from meridian.research_stage import CanonicalResearchStage
kind = CASE
load = app.load_policies
def configured(path):
    p = load(path)
    return replace(p, models=p.models.model_copy(update={'research': p.models.research.model_copy(update={'live_enabled':True,'llm_max_retries':0})}))
app.load_policies = configured
def runner(command, input_text, environment, cwd, timeout):
    if kind == 'missing': raise FileNotFoundError('injected')
    if kind == 'timeout': raise TimeoutError('injected')
    if kind == 'auth': return ProcessResult(returncode=1,stderr='sign in required')
    path=Path(command[command.index('--output-last-message')+1])
    if kind == 'malformed':
        path.write_text('invalid',encoding='utf-8')
        return ProcessResult(returncode=0)
    facts=json.loads(input_text)['signals']
    results=[{'ticker':'AAPL','direction':'NEUTRAL','research_conviction':0.1,
      'thesis':'Regression-only inference','claim_kind':'MODEL_INFERENCE',
      'risks':['fixture'],'cited_evidence_ids':[facts[0]['evidence_reference']],
      'data_limitations':['Synthetic public inputs']}]
    if kind == 'schema': del results[0]['direction']
    output={'status':'OK','summary':'bounded','market_regime':'unknown',
      'evidence':[],'contradictions':[],'risks':[],'data_gaps':[],
      'confidence':0.1,'recommended_action':'HOLD',
      'recommended_exposure_change':'MAINTAIN','rationale':'bounded',
      'assumptions':[],'warnings':[],'results':results}
    path.write_text(json.dumps(output),encoding='utf-8')
    return ProcessResult(returncode=0)
provider=CodexCliProvider(executable='codex-test.exe',runner=runner,environment={})
app.CanonicalResearchStage = lambda: CanonicalResearchStage(provider=provider)
raise SystemExit(main())
""".replace("CASE", repr(kind))
    exit_code, result = cli(tmp_path, ["daily", "--snapshot", str(account), "--market-fixture", str(quote_file), "--json"], code=code)
    assert exit_code == 0 and result["runtime_status"] == "PASS"
    assert result["research_status"] == status
    assert result["decision_context"]["research_status"] == status
    assert result["readiness"]["recommendation_readiness"] == "BLOCKED"
    assert not result["manual_authority"]["certificate_issued"]
    markdown = Path(result["report_markdown"]).read_text(encoding="utf-8")
    assert "Account freshness" in markdown and "Market freshness" in markdown and status in markdown
@pytest.mark.parametrize("fault", ["timeout", "dns", "invalid"])
def test_yahoo_provider_faults_are_structured(fault: str):
    from test_operational_data import NOW, Provider

    from meridian.operational_data import OperationalRefreshService
    from meridian.quotes import (
        QuoteProviderTimeout,
        YahooChartQuoteProvider,
    )
    from meridian.security_master import DEFAULT_SECURITY_MASTER
    def opener(*args, **kwargs):
        if fault == "timeout":
            raise TimeoutError("injected")
        if fault == "dns":
            raise OSError("injected DNS failure")
        class Invalid:
            status = 200
            def read(self):
                return b"invalid payload"
        return Invalid()
    result = OperationalRefreshService(YahooChartQuoteProvider(DEFAULT_SECURITY_MASTER, opener=opener),
        Provider("secondary", QuoteProviderTimeout())).refresh("AAPL", analysis_time=NOW)
    assert result.selected is None
    assert result.primary.status.value in {"UNAVAILABLE", "INVALID_RESPONSE"}
    assert result.secondary.status.value == "UNAVAILABLE"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows PowerShell 5 launcher")
def test_launcher_missing_python_is_structured(tmp_path: Path):
    import shutil
    launcher = tmp_path / "installation # 中文" / "scripts" / "run_meridian.ps1"
    launcher.parent.mkdir(parents=True)
    shutil.copyfile(Path(__file__).parents[1] / "scripts/run_meridian.ps1", launcher)
    run = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", str(launcher), "daily", "--json"], cwd=tmp_path,
        capture_output=True, text=True, encoding="utf-8", timeout=20, check=False)
    assert run.returncode == 3
    result = json.loads(run.stdout)
    assert result["error_code"] == "MERIDIAN_PYTHON_MISSING"
    assert result["run_id"] and result["next_actions"] and result["output_files"] == {}
