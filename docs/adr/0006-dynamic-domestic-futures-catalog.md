# ADR 0006: Dynamic domestic futures instrument catalog

- Status: Accepted
- Date: 2026-10-15

## Context

The platform was originally wired to several red-date contracts. Supporting every
listed futures product on SHFE/INE, DCE, CZCE, CFFEX and GFEX cannot rely on a
hand-maintained contract list: delivery months change continuously and inactive
contracts must not be presented as live.

## Decision

Use Sina's public futures product directory and per-product `getNameList` response
as the observed instrument catalog. Refresh it in the Python market collector,
persist the last successful catalog beside market snapshots, and expose it through
the Java market service. Canonical API main-contract symbols use `M`; provider-only
continuous symbols use `0`.

Quote collection is batched in the background for all catalog symbols. Historical
K-lines remain lazy and are fetched only for requested symbols. This keeps user
requests independent from upstream latency while avoiding an all-contract history
storm. Failed refreshes retain the last observed catalog and mark it `DEGRADED`.

Product-specific evidence is never reused for an unrelated product. If a genuine
news, rule or production-weather observation is unavailable, that dimension is
returned as `UNAVAILABLE` and excluded by the existing fusion normalization.

## Consequences

- New listings appear after a catalog refresh without a deployment.
- A cold start needs the catalog collector to warm up; persisted snapshots remove
  this delay after the first successful run.
- Sina is still a single upstream provider. The cache and explicit status preserve
  availability and honesty, but a second licensed feed remains the production
  hardening path.

