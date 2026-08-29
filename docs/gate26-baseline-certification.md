# Gate 2.6 Baseline Certification

The Gate 3B.1 work started from the first durable Git baseline:

- HEAD: `fb4850b` (`Gate 2.6 safety convergence baseline`)
- Branch: `main`
- Baseline tests: 101 passed
- Baseline ruff: passed
- Baseline pyright: passed
- `.env.local`, virtualenv, artifacts, runtime state and vendor cache were
  ignored and were not included in the commit.

The supplied Gate 2.6 report matched the local baseline, so Gate 3B.1 work
was allowed to proceed. No secret file was read.

