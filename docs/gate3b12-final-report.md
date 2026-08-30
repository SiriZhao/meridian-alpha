# Gate 3B.12 — real certified signal and alpha shadow

## Result

The live certified chain is now real and fail-closed:

`CERTIFIED_HISTORICAL_PIT SEC evidence → LIVE_SHADOW DeepSeek → GroundedResearchSignal → EvidenceAuthorizationService → CertifiedAgentSignal`.

The V5 run used a synthetic host-style account and carried the final authorization `SHADOW / NOT AUTHORIZED FOR ENTRY`. It has no broker, Schwab, real-account, order, sizing, or execution interface.

## Live results

- Real PIT-certified evidence: AAPL, NVDA, and (via historical submissions lookup) MSFT.
- Real grounded signals: 2 (AAPL, NVDA).
- Real CertifiedAgentSignals: 2, each authorization-issued and citing one exact SEC item.
- DeepSeek result: both outputs were valid, cited, and `NEUTRAL` at 0.5 conviction.
- First non-zero LLM alpha: **No**. Base research modifier was zero for both signals because neutral is governed as zero. No special case was added to force a result.
- Dislocation: deterministic screen had no eligible candidates; `ABSTAIN`, modifier zero, no additional model call.

## Alpha and lineage

Base grounded research is capped at `0.18`; dislocation may contribute only incrementally, and the combined research contribution is capped at `0.20`. The V5 report identifies the quant input, certificate ID, exact evidence IDs, response-artifact hash, base/dislocation/combined modifiers, risk penalty, final alpha, and pre/post-risk target. The response artifacts hold only validated structured output, safe metadata, IDs, diagnostics, and content hashes—never credentials, headers, account data, or hidden reasoning.

The observed V5 values were:

- AAPL: quant `-0.01841591977111094265018527733`; LLM modifier `0`; final alpha `-0.008287163896999924192583374798`.
- NVDA: quant `0.2775292342338071115420204368`; LLM modifier `0`; final alpha `0.1248881554052132001939091966`.

## SEC and identity

The SEC submissions adapter now searches bounded authoritative historical collection files when an exact accession is absent from `filings.recent`. It preserves the actual collection URI, content hash, retrieval time, exact CIK/accession identity, and `acceptanceDateTime`; it never infers a filing timestamp.

The bounded Security Master now has all 11 required records, including META and GOOGL. Authoritative provenance promotion remains `0/11`; these records therefore remain development-verified, not artificially promoted.

## Release decision

- Known P0: none.
- Known P1: the real model outputs were neutral, so the non-zero LLM-alpha milestone was not met; authoritative Security Master provenance remains incomplete; no eligible real dislocation candidate was screened.
- `REAL_LLM_ALPHA_BREAKTHROUGH`: not claimed.
- Safe next state: continue certification and future bounded shadow runs; do not weaken evidence, citation, or alpha rules.