# Gate 3B.11 — Live LLM transport convergence

## Outcome

The explicit `LIVE_SHADOW` transport path converged on 2026-08-30. A minimal prior probe and the bounded certified AAPL/NVDA grounding run both returned HTTP 200 OpenAI-compatible envelopes with non-empty assistant content. Both grounding results passed strict JSON parsing, Meridian schema validation, and exact evidence-citation validation.

The default `research.live_enabled` remains `false`. The direct transport is reachable only through the existing explicit shadow opt-in and still has no account, broker, order, sizing, or execution authority.

## Boundary

The executable prompt contains only the ticker, decision timestamp, research profile, and exact contents of `CertifiedEvidenceView`. It excludes Yahoo, raw `ResearchContextPacket`, synthetic/replay material, TradingAgents output, account data, targets, and order intent.

The canonical extractor accepts only supported OpenAI-compatible `choices[0].message` content or an explicit structured object. It accepts valid JSON and exactly one outer JSON fence. It never recovers fields from prose. Any missing required field, invalid JSON, invalid provider envelope, unknown evidence identifier, wrong-ticker citation, timeout, HTTP failure, or abstention is fail-closed and cannot produce a signal.

## Sanitized transport stages

`REQUEST_PREPARED`, `CLIENT_CREATED`, `HTTP_ATTEMPTED`, `HTTP_COMPLETED`, `RESPONSE_RECEIVED`, `PROVIDER_ENVELOPE_PARSED`, `ASSISTANT_CONTENT_PRESENT`, `STRUCTURED_PAYLOAD_EXTRACTED`, `MERIDIAN_SCHEMA_VALID`, `CITATIONS_VALID`, and `GROUNDING_RESULT_CREATED` are retained in the outcome diagnostics. They contain no API key, authorization header, environment value, prompt, or hidden reasoning.

A validated structured payload is now attached solely to the sanitized outcome for replay. The two successful calls that established convergence occurred immediately before that final storage field was attached; they were not repeated in order to respect the two-call primary budget. Future successful shadow responses can be replayed without a new provider call.

## Live result

- AAPL: AVAILABLE; 1 exact certified SEC citation; HTTP 200; 5,108 ms.
- NVDA: AVAILABLE; 1 exact certified SEC citation; HTTP 200; 10,593 ms.
- Certified signals: 2 in the bounded shadow run.
- Authorization: `SHADOW / NOT AUTHORIZED FOR ENTRY`.

No credential, real account, broker, order, or FinRL-X promotion was used.