# ADR-0004: Separate empirical signals from cultural references

## Status

Accepted

## Context

The product must restore eleven-dimensional analysis without reintroducing hard-coded or synthetic market evidence. The user also wants Liu Yao, I Ching, and Qi Men Dun Jia outputs calculated from the real request time. These cultural systems are not empirically validated market inputs and must not alter trading decisions.

## Decision

The prediction response contains two explicitly separated groups:

- Eleven `EMPIRICAL` dimensions. Each carries source, observation time, sample size, availability status, weight, and a score only when observed inputs are available.
- Three `CULTURAL_REFERENCE` dimensions. They are calculated deterministically from the Asia/Shanghai request time and calendar data, always have weight `0`, `includedInScore=false`, and no numeric trading score.

The fusion engine normalizes weights over available empirical dimensions only. Missing upstream evidence produces `UNAVAILABLE`; it never produces a default score. The frontend visually separates cultural references and states that they do not affect signal, position, target, or stop-loss values.

## Consequences

### Positive

- Eleven-dimensional quantitative analysis remains auditable.
- Missing data cannot silently become fabricated evidence.
- Cultural material remains available without being misrepresented as financial evidence.
- The API contract makes scoring inclusion machine-verifiable.

### Negative

- Some dimensions may temporarily show unavailable when public upstreams fail.
- The response and frontend become more complex.
- Public sources have latency and rate-limit risk, requiring bounded timeouts and caching.

### Neutral

- Cultural calculations use a calendar library but remain interpretive content.

## Alternatives Considered

- Keep the original hard-coded engines: rejected because the values are not observed.
- Include cultural results with small weights: rejected because any non-zero weight would contaminate the empirical trading score.
- Remove cultural dimensions entirely: rejected because the user explicitly requested them as clearly marked reference material.

