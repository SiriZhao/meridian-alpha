# ADR-010: Canonical public advisory research

Accepted for engineering integration; live acceptance remains blocked.

## Actual call chain

Before: application_cli → MeridianApplicationService.daily → snapshot inspection
and claim → OperationalMarketSnapshotService → DailyClosureService → deterministic
allocation/risk/reconciliation/order draft → AuditStore/reports. Canonical research
was always NOT_RUN. Existing DeepSeekGroundedResearchNormalizer requires sealed
certified evidence and was not called by this public operational path.

After: the same chain inserts CanonicalResearchStage between validated observations
and DailyClosureService. DailyResearchInput binds parent run, cutoff, hashed account,
market and policy references, provider/model, prompt version and input hash.
Only allowlisted public price/return/timestamp/citation fields leave the process.
ResearchDecisionContext is validated against the decision run and cutoff and is
retained with the deterministic result. No second daily CLI or broker API exists.

## Authority and facts

SymbolResearch extends existing GroundedResearchResult. Exact symbol coverage,
input citations, MODEL_INFERENCE and limitations are required. The schema and
citations validate structure/reference membership, not factual truth of model prose.
Narrative is rendered literally and cannot become account facts or financial inputs.
Bullish/bearish research produces identical financial decisions for identical inputs.
Public advisory research is not fed into the sealed-evidence normalizer.

Seven diagnostic gates include actual outcomes, reasons and evidence references.
They do not issue ManualReadinessCertificate. Research remains advisory, security
metadata uncertified, and public quotes cannot pass execution certification.
Aggregation blocks manual authority whenever any diagnostic gate is not PASS;
even diagnostic success would still require the existing sealed authority issuer.

## Runtime and reproducibility

The actual schema-validated research response is also its availability probe.
Credential presence alone is never AVAILABLE. Existing research configuration and
model remain unchanged; disabled research is NOT_RUN. Freshness is checked before
request and again at decision time, so LLM latency cannot preserve expired inputs.
One universe request respects the existing ticker budget. Each request has a maximum
60-second transport timeout, at most two retries, and at most two-second backoff;
only network/timeouts/429/5xx retry. Transport timeout is a socket timeout, not a hard
process wall-clock deadline. Response validation caps accepted bytes at 128 KiB;
the shared legacy HTTP helper still reads the response before that check.

Injected transport is always FIXTURE; fixture inputs cannot invoke live HTTP.
Replay requires an explicitly supplied original recorded artifact, identical input
hash, valid citations, receipt before replay time and permitted age. No automatic
cache fallback or CLI replay flag is introduced. Reuse the original artifact for
each replay; a replay-rendered result is not a new provider observation. Replay of
recorded output is reproducible; rerunning an external model is not guaranteed so.

Research timestamps, attempts, safe errors, stage latency, context and gate results
are stored in existing SQLite v2 run_readiness JSON and operator reports. No schema
upgrade is required. Account contents, credentials, prompts and raw HTTP bodies are
not added to audit storage. Fixed failure codes replace provider exception prose;
raw and decoded credential echoes are rejected. Arbitrary obfuscated exfiltration
is not a guarantee this string check can prove absent.

## Acceptance boundary

Deterministic transport tests establish pathway behavior, not real provider success.
Real Host authentication, fresh live inputs, actual LLM response acceptance and the
certified research-to-manual workflow still require independent evidence. Report
and SQLite writes retain their existing separate atomicity boundaries.
