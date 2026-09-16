from pathlib import Path
p=Path("src/meridian/application.py")
s=p.read_text(encoding="utf-8")
old='''            research = ResearchStageResult(
                context=ResearchDecisionContext(
                    research_run_id="native-" + parent_id,
                    parent_run_id=parent_id,
                    input_hash=request.input_hash,
                    analysis_cutoff=cutoff,
                    status=ResearchProviderStatus.NOT_RUN,
                ),
'''
new='''            native_status = (
                ResearchProviderStatus.CODEX_TIMEOUT
                if any(
                    stage.status.value == "TIMEOUT"
                    for stage in native_result.stages.values()
                )
                else ResearchProviderStatus.CODEX_PROCESS_ERROR
                if any(
                    stage.status.value in {"PROCESS_ERROR", "AUTH_ERROR", "NOT_AVAILABLE"}
                    for stage in native_result.stages.values()
                )
                else ResearchProviderStatus.INVALID_RESPONSE
            )
            research = ResearchStageResult(
                context=ResearchDecisionContext(
                    research_run_id="native-" + parent_id,
                    parent_run_id=parent_id,
                    input_hash=request.input_hash,
                    analysis_cutoff=cutoff,
                    status=native_status,
                ),
'''
if old not in s: raise SystemExit("missing native result status block")
s=s.replace(old,new,1)
p.write_text(s,encoding="utf-8")
