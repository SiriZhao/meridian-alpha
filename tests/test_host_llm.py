import pytest

from meridian.host_llm import (
    HostHandoffError,
    HostJobStage,
    HostLLMResult,
    accept_result,
    create_job,
    load_job,
)
from meridian.runtime import RuntimePaths
from meridian.runtime_io import atomic_write


def test_host_job_result_contract(tmp_path):
    job, job_path = create_job(
        RuntimePaths(tmp_path),
        run_id="host-run-20260915",
        stage=HostJobStage.RESEARCH,
        market_context={"source": "structured"},
        portfolio_context=None,
        risk_context={},
        strategy_context={},
        research_questions=("Assess supplied evidence",),
        required_output_schema={"type": "object"},
    )
    loaded = load_job(job_path)
    result_path = job_path.parent / "result.json"
    atomic_write(
        result_path,
        HostLLMResult(
            job_id=job.job_id,
            run_id=job.run_id,
            status="OK",
            summary="Evidence is mixed.",
            market_regime="NEUTRAL",
            confidence=0.5,
            evidence=("e1",),
        ).model_dump_json(),
    )
    result, accepted = accept_result(loaded, result_path)
    assert result.status == "OK" and accepted.is_file()
    stale = result_path.with_name("stale.json")
    atomic_write(stale, result.model_copy(update={"job_id": "job-stale"}).model_dump_json())
    with pytest.raises(HostHandoffError, match="HOST_LLM_RESULT_STALE"):
        accept_result(job, stale)


def test_host_invalid_result(tmp_path):
    job, job_path = create_job(
        RuntimePaths(tmp_path),
        run_id="host-run-20260915",
        stage=HostJobStage.RESEARCH,
        market_context={},
        portfolio_context=None,
        risk_context={},
        strategy_context={},
        research_questions=(),
        required_output_schema={},
    )
    bad = job_path.parent / "bad.json"
    atomic_write(bad, "{}")
    with pytest.raises(HostHandoffError, match="HOST_LLM_RESULT_INVALID"):
        accept_result(job, bad)
