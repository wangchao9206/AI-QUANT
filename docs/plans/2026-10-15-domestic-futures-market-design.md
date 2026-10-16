# Domestic Futures Market Coverage Design

**Goal:** Replace red-date-only navigation and collection with real, discoverable
coverage of all currently listed domestic futures products and contracts.

## Architecture

`InstrumentCatalog` discovers exchange/product nodes from Sina's current public
directory, resolves every node to its observed contract symbols, and stores the
result in the existing durable feed snapshot. `LiveMarketFeed` consumes that
catalog, batches quotes in groups of 100, and lazily refreshes history for symbols
actually requested by users. FastAPI publishes the catalog and generalized term
curves; the Spring market service proxies the catalog and continues persisting
requested quote/curve snapshots to PostgreSQL. Vue renders a searchable selector
and never substitutes demo data.

## Reliability and concurrency

- No public upstream call runs on an HTTP request path.
- Catalog, quotes and history have separate refresh schedules and failure states.
- Quote batches are bounded and parallel; history refreshes are deduplicated.
- Persisted observed timestamps are retained across restarts and outages.
- Optional term-structure failure does not blank quote/history/prediction panels.

## Evidence contract

The eleven empirical slots remain stable. Price-derived dimensions generalize to
all products. News and trading-rule evidence are filtered by the selected product.
The production-weather dimension is only populated where a real product-region
adapter exists; otherwise it is visibly `UNAVAILABLE`. Cultural calculations keep
their approved 3% weights and remain marked `非实证文化参考`.

