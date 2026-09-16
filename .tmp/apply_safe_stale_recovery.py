from pathlib import Path
p=Path("src/meridian/application.py")
s=p.read_text(encoding="utf-8")
old='''            if semantic_quote_payload(frozen_quotes) != semantic_quote_payload(research_quotes):
                # The first stale result starts a new bounded decision cycle.
                # Never reuse its result; the newly-created job is explicit
                # about requiring the host to reason over the new snapshot.
                host_job_path = None
                host_result_path = None
                host_resume_job = None
                startup["host_llm_recovery"] = {
                    "status": "REBUILT",
                    "reason": "HOST_LLM_RESULT_STALE",
                    "old_run_id": host_resume_job.run_id if host_resume_job else None,
                }
            else:
                # Resume uses the exact research snapshot from the job. A later
                # provider poll may update timestamps without changing decision facts.
                research_quotes = frozen_quotes
'''
new='''            if semantic_quote_payload(frozen_quotes) != semantic_quote_payload(research_quotes):
                # The first stale result starts a new bounded decision cycle.
                # Never reuse its result; explicitly create a new host job.
                old_run_id = host_resume_job.run_id
                from meridian.host_llm import HostLLMResult
                rebuilt_job, rebuilt_path = create_job(
                    self.paths,
                    run_id=parent_id,
                    stage=HostJobStage.RESEARCH,
                    market_context={
                        "cutoff": cutoff.isoformat(),
                        "quotes": {k: v.model_dump(mode="json") for k, v in research_quotes.items()},
                    },
                    portfolio_context=portfolio_context,
                    risk_context={"gates": list(input_blockers)},
                    strategy_context={
                        "mode": "PAPER_ONLY",
                        "execution_authority": "NONE",
                        "market_reference": digest(
                            {k: v.model_dump(mode="json") for k, v in research_quotes.items()}
                        ),
                    },
                    research_questions=("Assess the supplied current market evidence.",),
                    required_output_schema=HostLLMResult.model_json_schema(),
                )
                host_job_path = str(rebuilt_path)
                host_result_path = None
                host_resume_job = rebuilt_job
                startup["host_llm_recovery"] = {
                    "status": "REBUILT",
                    "reason": "HOST_LLM_RESULT_STALE",
                    "old_run_id": old_run_id,
                    "new_job_path": str(rebuilt_path),
                }
            else:
                # Resume uses the exact research snapshot from the job. A later
                # provider poll may update timestamps without changing decision facts.
                research_quotes = frozen_quotes
'''
if old not in s: raise SystemExit("missing stale recovery block")
s=s.replace(old,new,1)
p.write_text(s,encoding="utf-8")
