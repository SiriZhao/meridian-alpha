"""Regression evidence for defects found during the final maintainer review."""
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from meridian.analytics.derived_market_features import derive_market_features
from meridian.astra_research import (
    AuditMetadata,
    ClaimKind,
    MeridianResearchResult,
    ResearchClaim,
    ResearchEvidence,
    ResearchIntent,
)
from meridian.evidence_graph import EvidenceGraph
from meridian.fundamentals import (
    CanonicalMetric,
    build_snapshot,
    canonical_definition,
    classify_context,
)
from meridian.market import Bar
from meridian.mcp_server import account_snapshot, quant_metrics, risk_analysis
from meridian.schemas import AccountSnapshot
from tests.test_fundamentals import fact

NOW = datetime(2026, 9, 11, tzinfo=UTC)


def test_ytd_and_gap_use_prior_year_close_and_current_open():
    bars = tuple(Bar(timestamp=t, open=Decimal(o), high=Decimal('130'), low=Decimal('90'), close=Decimal(c), volume=100)
                 for t, o, c in [(datetime(2025, 12, 31, tzinfo=UTC), '100', '100'),
                                 (datetime(2026, 1, 2, tzinfo=UTC), '110', '115'),
                                 (NOW, '120', '125')])
    result = derive_market_features(bars, as_of=NOW)
    assert result['return_ytd'] == Decimal('0.25')
    assert result['gap'] == Decimal('120') / Decimal('115') - 1
    for name in ('average_volume_20d', 'realized_volatility_20d', 'distance_52w_high', 'beta_60d'):
        assert result[name] is None
    assert derive_market_features(bars, as_of=NOW, benchmark_bars=bars)['relative_performance_spy_20d'] is None


@pytest.mark.parametrize('field', ['known_at', 'observed_at'])
def test_result_cutoff_is_authoritative_over_evidence_cutoff(field):
    payload = dict(evidence_id='e', source='fixture', provenance='fixture', freshness='UNKNOWN',
                   data_quality='UNKNOWN', observed_at=NOW, known_at=NOW, analysis_cutoff=NOW + timedelta(days=2))
    payload[field] = NOW + timedelta(days=1)
    evidence = ResearchEvidence.model_validate(payload)
    with pytest.raises(ValueError, match='RESULT_EVIDENCE_AFTER_CUTOFF'):
        MeridianResearchResult(subject='GOOGL', research_question='q', intent=ResearchIntent.COMPANY_RESEARCH, analysis_cutoff=NOW, evidence=(evidence,))


def test_result_rejects_claim_type_confidence_and_authority_spoofing():
    with pytest.raises(ValueError):
        AuditMetadata.model_validate({'execution_authority': 'BROKER'})
    base = dict(subject='GOOGL', research_question='q', intent='COMPANY_RESEARCH', analysis_cutoff=NOW)
    with pytest.raises(ValueError, match='SECTION_MISMATCH'):
        MeridianResearchResult.model_validate({**base, 'facts': [ResearchClaim(kind=ClaimKind.INFERENCE, statement='x')]})
    with pytest.raises(ValueError, match='CONFIDENCE_REQUIRES_EVIDENCE'):
        MeridianResearchResult.model_validate({**base, 'confidence': 0.9})


def test_graph_rejects_cycles_and_unsupported_confidence():
    with pytest.raises(ValueError, match='CYCLE'):
        EvidenceGraph.model_validate({'nodes': [{'node_id': 'a', 'node_type': 'ASSUMPTION', 'statement': 'a'}],
            'relationships': [{'from_node_id': 'a', 'to_node_id': 'a', 'relation': 'DEPENDS_ON'}]})
    with pytest.raises(ValueError, match='UNSUPPORTED'):
        EvidenceGraph.model_validate({'claims': [{'claim_id': 'c', 'claim_type': 'FACT', 'statement': 'x', 'confidence': 1}]})


def test_sec_filing_label_does_not_override_fact_duration():
    assert classify_context(period_start=date(2026, 7, 1), period_end=date(2026, 9, 30), form='10-K', fiscal_period='FY').value == 'QUARTER'
    assert canonical_definition('dei', 'EntityCommonStockSharesOutstanding') is not None


def test_yoy_does_not_use_an_arbitrary_prior_quarter():
    current = fact('REVENUE', '100')
    assert current.period_start is not None
    prior = current.model_copy(update={'fact_id': 'prior', 'period_start': current.period_start - timedelta(days=90), 'period_end': current.period_end - timedelta(days=90)})
    assert not build_snapshot('AAPL', (current, prior), NOW).comparable_series


def test_debt_deduplicates_components_and_keeps_one_accession():
    seed = fact('LONG_TERM_DEBT', '10')
    current = seed.model_copy(update={'fact_id': 'current', 'concept': 'LongTermDebtCurrent', 'raw_concept': 'LongTermDebtCurrent', 'period_start': None})
    noncurrent = current.model_copy(update={'fact_id': 'noncurrent', 'concept': 'LongTermDebtNoncurrent', 'raw_concept': 'LongTermDebtNoncurrent', 'value': Decimal('90')})
    result = build_snapshot('AAPL', (current, current, noncurrent, noncurrent), NOW)
    assert result.facts[0].canonical_metric == CanonicalMetric.LONG_TERM_DEBT
    assert result.facts[0].value == 100
    incomplete = build_snapshot('AAPL', (current, current), NOW)
    assert not incomplete.facts


@pytest.mark.parametrize('modification', [{'close': 'Infinity'}, {'open': '200'}, {'volume': None}])
def test_quant_rejects_malformed_bars(modification):
    row = {'observed_at': NOW.isoformat(), 'open': '100', 'high': '110', 'low': '90', 'close': '100', 'volume': 10}
    result = quant_metrics('GOOGL', [{**row, **modification}], NOW)
    assert result['status'] == 'REJECTED'
    assert result['execution_authority'] == 'NONE'


@pytest.mark.parametrize('offset', [-3601, 1])
def test_account_and_risk_reject_spoofed_freshness(offset):
    account = AccountSnapshot(snapshot_id='fixture', account_alias='sanitized', provider='fixture',
        as_of=NOW + timedelta(seconds=offset), total_equity=Decimal('100'), cash=Decimal('100'),
        freshness_state='VERIFIED', sync_state='SYNCED')
    assert not account_snapshot(account, NOW)['valid']
    result = risk_analysis(account, NOW)
    assert result['status'] == 'REJECTED' and result['gross_exposure'] is None


def test_ttm_requires_four_nonoverlapping_quarters_and_resolvable_inputs():
    dates = [(date(2025, 7, 1), date(2025, 9, 30)), (date(2025, 10, 1), date(2025, 12, 31)),
             (date(2026, 1, 1), date(2026, 3, 31)), (date(2026, 4, 1), date(2026, 6, 30))]
    quarters = tuple(fact('REVENUE', str((i + 1) * 10)).model_copy(update={
        'fact_id': f'q{i}', 'period_start': datetime.combine(start, datetime.min.time(), UTC),
        'period_end': datetime.combine(end, datetime.min.time(), UTC)}) for i, (start, end) in enumerate(dates))
    result = build_snapshot('AAPL', quarters, NOW)
    ttm = next(item for item in result.derived if item.metric == 'REVENUE_TTM')
    assert ttm.value == 100
    assert set(ttm.input_fact_ids) <= {item.fact_id for item in result.quarterly_history}
    assert not any(item.metric.endswith('_TTM') for item in build_snapshot('AAPL', quarters[1:], NOW).derived)


def test_astra_surface_has_no_nested_daily_pipeline():
    from meridian.mcp_server import registered_tool_names
    assert not {'run_host_daily_analysis', 'run_daily_analysis'} & registered_tool_names()


@pytest.mark.parametrize('error', [ValueError('malformed'), TypeError('malformed'), TimeoutError('timeout')])
def test_provider_failures_preserve_explicit_diagnostics(error):
    from meridian.data.retrieval_orchestrator import RetrievalOrchestrator
    from tests.retrieval_helpers import requirement

    class BrokenProvider:
        provider_name = 'broken-fixture'

        def supports(self, requirement):
            return True

        def retrieve(self, requirement, *, as_of):
            raise error

    result = RetrievalOrchestrator([BrokenProvider()], max_retries=0).retrieve((requirement(),), as_of=NOW)
    assert not result.evidence
    assert result.provider_results[0].failure is not None


def test_sec_numerical_retrieval_requires_acceptance_metadata(monkeypatch):
    from meridian.data.providers.base import RetrievalProviderError
    from meridian.data.providers.structured import SecFundamentalRetrievalProvider
    from meridian.fundamentals import CertifiedFundamentalSnapshot
    from tests.retrieval_helpers import requirement
    monkeypatch.setattr('meridian.data.providers.structured.certified_company_snapshot',
                        lambda *args, **kwargs: (None, CertifiedFundamentalSnapshot(ticker='NVDA', decision_as_of=NOW)))
    with pytest.raises(RetrievalProviderError, match='CERTIFIED_FUNDAMENTAL_DATA_MISSING'):
        SecFundamentalRetrievalProvider().retrieve(requirement(), as_of=NOW)


def test_sec_provider_rejects_timezone_less_acceptance():
    import json

    from meridian.sec_filing_metadata import SECSubmissionMetadataProvider

    class Response:
        def read(self):
            return json.dumps({'cik': '0000320193', 'filings': {'recent': {
                'accessionNumber': ['0000320193-26-000001'], 'acceptanceDateTime': ['2026-08-30T12:00:00'],
                'form': ['10-Q'], 'filingDate': ['2026-08-30'], 'primaryDocument': ['filing.htm']}}}).encode()
    provider = SECSubmissionMetadataProvider(opener=lambda *args, **kwargs: Response())
    with pytest.raises(ValueError, match='SEC_ACCEPTANCE_TIMEZONE_REQUIRED'):
        provider.get_metadata('0000320193', '0000320193-26-000001')
