from pathlib import Path
p=Path("src/meridian/application.py")
s=p.read_text(encoding="utf-8")
needle = """        expected_closed_market = (
            current_market.status is not MarketStatus.OPEN
            and market_error is None
            and research_inputs_ready
        )
"""
replacement = needle + """        host_job_path = os.environ.get("MERIDIAN_HOST_JOB")
"""
if needle not in s:
    raise SystemExit("missing expected market block")
s=s.replace(needle,replacement,1)
p.write_text(s,encoding="utf-8")
