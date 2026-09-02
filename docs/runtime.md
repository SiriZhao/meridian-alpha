# Runtime directories and local diagnostics

Meridian keeps mutable state outside the installed package. On Windows the
default home is `%LOCALAPPDATA%\MeridianAlpha`; set an absolute
`MERIDIAN_HOME` to override it (tests should set it to a temporary directory).

The runtime layout is `data/`, `db/`, `cache/`, `reports/`, `logs/`, `runs/`,
`audit/`, and `config/`. The canonical SQLite location is
`db/meridian.sqlite3`. A missing database is reported as `PENDING`; Meridian
must not silently create an alternate database in the working directory.

Run the bounded, local-only diagnostic before stateful work:

```powershell
.\.venv\Scripts\python.exe -m meridian.runtime_diagnostics doctor --json
.\scripts\run_meridian.ps1 doctor --json
```

The report is machine-readable and never performs network probes. It reports
secret state only as `configured=true|false`. A database marked `PENDING`
requires explicit initialization by the existing audit migration path; a
`FAILED` migration/database state blocks readiness and must not be ignored.

`scripts/run_meridian.ps1` is a thin Windows launcher. It runs the diagnostic,
propagates its exit code, then delegates to the established CLI; it contains no
business or brokerage logic.
