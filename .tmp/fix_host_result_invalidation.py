from pathlib import Path
p=Path("src/meridian/application.py")
s=p.read_text(encoding="utf-8")
s=s.replace('''        host_resume_job = None
        if host_job_path:
''','''        host_resume_job = None
        host_result_invalidated = False
        if host_job_path:
''',1)
s=s.replace('''                host_job_path = str(rebuilt_path)
                host_result_path = None
                host_resume_job = rebuilt_job
''','''                host_job_path = str(rebuilt_path)
                host_result_path = None
                host_result_invalidated = True
                host_resume_job = rebuilt_job
''',1)
old='''        host_mode = os.environ.get("MERIDIAN_LLM_MODE", "").upper() == "HOST_CODEX"
        host_result_path = os.environ.get("MERIDIAN_HOST_RESULT")
        host_research: ResearchStageResult | None = None
'''
new='''        host_mode = os.environ.get("MERIDIAN_LLM_MODE", "").upper() == "HOST_CODEX"
        if not host_result_invalidated:
            host_result_path = os.environ.get("MERIDIAN_HOST_RESULT")
        host_research: ResearchStageResult | None = None
'''
if old not in s: raise SystemExit("missing host path assignment")
s=s.replace(old,new,1)
p.write_text(s,encoding="utf-8")
