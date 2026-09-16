from pathlib import Path
p=Path("src/meridian/application.py")
s=p.read_text(encoding="utf-8")
old='''        host_mode = os.environ.get("MERIDIAN_LLM_MODE", "").upper() == "HOST_CODEX"
        if not host_result_invalidated:
            host_result_path = os.environ.get("MERIDIAN_HOST_RESULT")
'''
new='''        host_mode = os.environ.get("MERIDIAN_LLM_MODE", "").upper() == "HOST_CODEX"
        if not host_result_invalidated:
            host_job_path = os.environ.get("MERIDIAN_HOST_JOB")
            host_result_path = os.environ.get("MERIDIAN_HOST_RESULT")
'''
if old not in s: raise SystemExit("missing guarded host assignment")
s=s.replace(old,new,1)
p.write_text(s,encoding="utf-8")
