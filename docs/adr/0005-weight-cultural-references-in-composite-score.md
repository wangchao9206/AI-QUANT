# ADR-0005: Weight labelled cultural references in the composite score

## Status

Accepted; supersedes the scoring-isolation decision in ADR-0004.

## Context

The approved afternoon model assigns a small weight to Liu Yao, I Ching, and Qi Men calculations. These calculations use the real Asia/Shanghai analysis time and deterministic traditional-calendar mappings. They are not empirically validated market evidence, so the product must not present them as such.

## Decision

- Keep the eleven empirical dimensions as a distinct response group with 91% total configured weight.
- Keep the three cultural dimensions as a separate `CULTURAL_REFERENCE` response group.
- Assign each cultural dimension a 3% weight, a numeric score, and `includedInScore=true`.
- Include all available empirical and cultural dimensions in the normalized composite score and confidence calculation.
- Display the phrase “非实证文化参考” prominently in the UI and in every cultural recommendation.
- Use a new model version so cached and persisted results from the former zero-weight model cannot be reused as the current result.

If any optional empirical input is unavailable, it remains `UNAVAILABLE` and is excluded; the remaining eligible weights are normalized. Market quotes, K-lines, term structure, weather, news, and trading rules continue to come from observed upstream data rather than demo constants.

## Consequences

The composite score now intentionally contains a 9% non-empirical component. Consumers can audit this through `category`, `weight`, `includedInScore`, source metadata, and the separate `culturalReferences` collection. The UI communicates the distinction without hiding the configured influence.
