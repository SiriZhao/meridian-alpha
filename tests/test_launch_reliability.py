"""Offline acceptance: launch identity, explicit gaps and isolated paper accounting."""
from decimal import Decimal
from pathlib import Path

from meridian.audit import AuditStore
from meridian.launch_identity import launch_identity
from meridian.paper import DEFAULT_ACCOUNT, PaperLedger, PaperOrderIntent
from meridian.research_order_review import plan_paper_review
from meridian.research_recommendations import build_recommendations
from meridian.terminal_service import TerminalPlanner
from tests.test_research_decisions import paper_account, planner_quotes, quant_request

ROOT = Path(__file__).resolve().parents[1]


def test_launch_identity_is_read_only_and_rejects_other_checkout(tmp_path, monkeypatch):
    home = tmp_path / 'not-created'
    monkeypatch.setenv('MERIDIAN_HOME', str(home))
    monkeypatch.setenv('MERIDIAN_CACHE', str(tmp_path / 'not-created-cache'))
    good = launch_identity(ROOT)
    assert good['status'] == 'PASS'
    assert good['challenger_mode'] == 'V2.3_SHADOW'
    assert good['environment']['challenger_engine_hash']
    assert good['environment']['policy_file_hashes']['models.yaml']
    assert not good['model_inference_actually_run'] and not good['runtime_written']
    assert not home.exists() and not (tmp_path / 'not-created-cache').exists()
    wrong = launch_identity(tmp_path)
    assert wrong['status'] == 'BLOCKED'
    assert 'WRONG_PACKAGE_ORIGIN' in wrong['blockers']
    assert 'WRONG_POLICY_DIRECTORY' in wrong['blockers']


def test_missing_history_has_traceable_stable_gap_requests():
    request = quant_request().model_copy(update={'histories': ()})
    snapshot = TerminalPlanner().build(request).quant
    first = build_recommendations(snapshot)
    assert first == build_recommendations(snapshot)
    for row in first:
        assert row.category == 'WAIT_FOR_EVIDENCE'
        assert row.data_gap_requests
        for gap in row.data_gap_requests:
            assert gap.analysis_cutoff == row.analysis_cutoff
            assert gap.snapshot_hash == row.snapshot_hash and gap.symbol == row.symbol
            assert gap.required_evidence and not gap.authorization_granted


def test_v23_paper_drafts_to_isolated_ledger_accounting_and_restart(tmp_path, monkeypatch):
    # Explicit test harness only. No application route promotes the challenger.
    monkeypatch.setenv('MERIDIAN_HOME', str(tmp_path / 'runtime'))
    monkeypatch.setenv('MERIDIAN_CACHE', str(tmp_path / 'cache'))
    request = quant_request(verified=True, regular=True)
    quotes, certificates, market = planner_quotes(request)
    paper = PaperLedger(AuditStore(tmp_path / 'fixture.sqlite3'))
    before, created = paper.initialize()
    assert created and before.cash == Decimal('100000')
    review = plan_paper_review(request, account=paper_account(request.analysis_cutoff),
        quotes=market, execution_quotes=quotes, certificates=certificates)
    assert review.paper_drafts and review.state == 'PAPER_ONLY'
    assert review.execution_authority == 'NONE' and review.manual_blockers
    assert all(d.preferred_limit is not None for d in review.paper_drafts)
    intents = tuple(PaperOrderIntent(f'fixture-{i}', d.ticker, d.side, d.quantity,
        d.preferred_limit or Decimal(0), 'CERTIFIED_CONTRACT_FIXTURE_NOT_REAL_QUOTE')
        for i, d in enumerate(review.paper_drafts))
    day = request.analysis_cutoff.date().isoformat()
    status, fills = paper.execute(DEFAULT_ACCOUNT, trading_date=day,
        canonical_run_id='FIXTURE_V23_ONLY', intents=intents, now=request.analysis_cutoff)
    assert status == 'PAPER_COMPLETE' and len(fills) == len(intents)
    after = paper.state()
    assert after is not None and after.cash >= 0
    spent = sum((f.quantity * f.fill_price + f.fees for f in fills), Decimal(0))
    assert before.cash - after.cash == spent
    assert sum((p.quantity for p in after.positions), Decimal(0)) == sum((f.quantity for f in fills), Decimal(0))
    restarted = PaperLedger(AuditStore(tmp_path / 'fixture.sqlite3'))
    duplicate, duplicate_fills = restarted.execute(DEFAULT_ACCOUNT, trading_date=day,
        canonical_run_id='FIXTURE_V23_REPEAT', intents=intents, now=request.analysis_cutoff)
    assert duplicate == 'PAPER_ALREADY_EXECUTED' and not duplicate_fills
    assert restarted.state() == after
