# Maintenance

## P0 — blocks daily operation

- Real portfolio acceptance needs a newly supplied sanitized Host snapshot.
- Live recommendation acceptance needs fresh market data. The observed Sunday
  run returned stale Yahoo quotes; it correctly persisted
  a blocked report. Recheck during a supported fresh-data session.

## P1 — reliability closure

- Canonical daily currently runs the bounded operational signal, not the
  certified research/LLM pipeline. Integrate the existing research service only
  with real certified evidence; preserve NOT_RUN until actually executed.
- Test locked/denied ACL runtime locations and installed-wheel daily under a
  genuinely read-only installation; unrelated-cwd wheel doctor is verified.
- Historical bar age/session checks and closed-market research-only reporting
  need review before interpreting overnight operational output.
- Optional research dependencies require an explicit environment installation
  profile; use inexact sync to preserve existing optional packages.

## P2

- Retire historical internal CLI modules/scripts after auditing their remaining
  test and external callers; the supported launcher/Skill no longer call them.
- Add bounded transient retry where provider evidence supports it. Existing
  primary/secondary failure states remain visible; never invent missing data.
- Improve readable report content and per-stage timing after live closure.

## Backlog

- Quant/LLM challengers, calibration, new factors and UI changes remain frozen
  until real daily acceptance is complete. No new engine or gate is needed.
