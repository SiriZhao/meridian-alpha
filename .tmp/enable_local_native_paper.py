from pathlib import Path
p=Path("src/meridian/application.py")
s=p.read_text(encoding="utf-8")
s=s.replace("""        host_job_path = os.environ.get("MERIDIAN_HOST_JOB")
        host_research: ResearchStageResult | None = None
""","""        host_research: ResearchStageResult | None = None
""",1)
old="""        previous_llm_mode = os.environ.get("MERIDIAN_LLM_MODE")
        os.environ["MERIDIAN_LLM_MODE"] = "HOST_CODEX"
        try:
            # Canonical paper runs prepare or resume the explicit host handoff.
            daily = self.daily(snapshot_path, research_live_enabled=True)
        finally:
            if previous_llm_mode is None:
                os.environ.pop("MERIDIAN_LLM_MODE", None)
            else:
                os.environ["MERIDIAN_LLM_MODE"] = previous_llm_mode
"""
new="""        previous_llm_mode = os.environ.get("MERIDIAN_LLM_MODE")
        explicit_host_handoff = bool(
            os.environ.get("MERIDIAN_HOST_JOB")
            or os.environ.get("MERIDIAN_HOST_RESULT")
        )
        if explicit_host_handoff:
            os.environ["MERIDIAN_LLM_MODE"] = "HOST_CODEX"
        try:
            # Normal local paper runs execute the configured native runtime.
            # HOST_CODEX is reserved for an explicit job/result handoff.
            daily = self.daily(snapshot_path, research_live_enabled=True)
        finally:
            if explicit_host_handoff:
                if previous_llm_mode is None:
                    os.environ.pop("MERIDIAN_LLM_MODE", None)
                else:
                    os.environ["MERIDIAN_LLM_MODE"] = previous_llm_mode
"""
if old not in s: raise SystemExit("missing paper mode block")
s=s.replace(old,new,1)
p.write_text(s,encoding="utf-8")
