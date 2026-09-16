from pathlib import Path
p=Path("src/meridian/application.py")
s=p.read_text(encoding="utf-8")
s=s.replace('from meridian.schemas import RunStatus', 'from meridian.schemas import MarketSnapshot, RunStatus')
old='''        daily_data_status = (
            "PASS"
            if market_valid
            else "MARKET_CLOSED"
            if expected_closed_market
            else "FAILED"
        )
        eligible_research_tickers = tuple(
'''
new='''        daily_data_status = (
            "PASS"
            if market_valid
            else "MARKET_CLOSED"
            if expected_closed_market
            else "FAILED"
        )

        def semantic_quote_payload(values: dict[str, MarketSnapshot]) -> dict[str, dict[str, object]]:
            return {
                ticker: {
                    key: value
                    for key, value in quote.model_dump(mode="json").items()
                    if key not in {"timestamp", "freshness_state"}
                }
                for ticker, quote in sorted(values.items())
            }

        host_resume_job = None
        if host_job_path:
            host_resume_job = load_job(Path(host_job_path))
            if host_resume_job.stage is not HostJobStage.RESEARCH:
                raise ValueError("HOST_LLM_RESULT_STALE")
            raw_job_quotes = host_resume_job.market_context.get("quotes", {})
            if not isinstance(raw_job_quotes, dict):
                raise ValueError("HOST_LLM_RESULT_STALE")
            try:
                frozen_quotes = {
                    str(ticker): MarketSnapshot.model_validate(value)
                    for ticker, value in raw_job_quotes.items()
                    if isinstance(ticker, str) and isinstance(value, dict)
                }
            except ValueError as error:
                raise ValueError("HOST_LLM_RESULT_STALE") from error
            if semantic_quote_payload(frozen_quotes) != semantic_quote_payload(research_quotes):
                raise ValueError("HOST_LLM_RESULT_STALE")
            # Resume uses the exact research snapshot from the job. A later
            # provider poll may update timestamps without changing decision facts.
            research_quotes = frozen_quotes

        eligible_research_tickers = tuple(
'''
if old not in s: raise SystemExit("missing insertion block")
s=s.replace(old,new,1)
old2='''            if host_job_path:
                job_path = Path(host_job_path)
                job = load_job(job_path)
                if job.stage is not HostJobStage.RESEARCH or job.strategy_context.get("market_reference") != request.market_reference:
                    raise ValueError("HOST_LLM_RESULT_STALE")
'''
new2='''            if host_job_path:
                job_path = Path(host_job_path)
                job = host_resume_job or load_job(job_path)
                if job.stage is not HostJobStage.RESEARCH or job.strategy_context.get("market_reference") != request.market_reference:
                    raise ValueError("HOST_LLM_RESULT_STALE")
'''
if old2 not in s: raise SystemExit("missing host block")
s=s.replace(old2,new2,1)
p.write_text(s,encoding="utf-8")
