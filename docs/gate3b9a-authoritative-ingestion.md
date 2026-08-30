# Gate 3B.9A authoritative ingestion

## Real SEC metadata ingestion

A bounded public SEC submissions ingestion path now retrieves filing metadata by
CIK and accession with a strict timeout and a project user agent. It requires
an explicit `acceptanceDateTime`, exact CIK response identity, exact accession,
and a content hash. It does not use filed-date midnight or period end as an
availability substitute.

The bounded live validation returned real SEC acceptance timestamps for AAPL
accession `0000320193-18-000145` (2018-11-05T13:01:40Z) and NVDA accession
`0001045810-26-000075` (2026-08-26T20:36:00Z). Each promoted only through the
separate `sec-edgar-accession-certified` provider identity. MSFT's selected
legacy fact accession was absent from its current submissions listing and
remained unverified.

## Status

- SEC real metadata ingestion: implemented and exercised against SEC.
- SEC acceptance timestamps acquired: 2.
- SEC PIT certified items: 2 bounded observations.
- Security Master records: 11 target symbols requested; existing default
  records are development-verified and no enum-only authoritative promotion was made.
- Authoritative verified: 0/11 newly promoted in this gate.
- Real certified evidence count: 2 observed items (AAPL, NVDA).
- Known P0: none.
- Known P1: durable provider ingestion/replay cache, MSFT metadata lookup over
  historical submissions files, and authoritative identity provenance for the
  remaining bounded universe.

No broker, account, order, or execution capability was added.