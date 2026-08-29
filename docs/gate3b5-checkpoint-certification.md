# Gate 3B.5 checkpoint certification

Baseline commit before Gate 3B work: `fb4850b03371cc8fc7d70723498bd736b2b3c51f`.

Validation was rerun on 2026-08-30 with the project-local Python 3.12.14
environment: 160 tests passed, Ruff passed, Pyright reported 0 errors,
warnings, and information messages, and `git diff --check` passed.

The system Python 3.14 is not the project runtime and cannot import the
`src`-layout package or find Pyright; that environment mismatch is not a
source regression. The local `.venv` is the certified validation runtime.

`.gitignore` excludes environment files, virtual environments, runtime
databases, caches, credentials/secrets, and review artifacts. No environment
or secret file was read. No broker, Schwab, account, order, or execution
surface was introduced.

The Gate 3B.5 checkpoint commit is recorded in the follow-up certification
commit so this document can contain its final immutable SHA.
