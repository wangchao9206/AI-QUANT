# Live market timeout recovery design

## Problem

The UI launches four requests together and clears every panel when any one exceeds the seven-second browser timeout. The Python service currently performs fresh Eastmoney HTTPS calls inside each API request. Eastmoney is timing out during TLS negotiation from both the host and Docker, while the existing Sina background collector remains responsive but is not connected to the API.

## Decision

Use `LiveMarketFeed` as the single market-data path for predictions, quotes, history, term structure, and Java background ingestion. It continuously collects observed Sina futures data, writes the last successful observations to the existing Docker volume, and serves thread-safe snapshots without waiting on an upstream request. `CJM` is mapped to Sina's `CJ0` provider symbol while responses retain the canonical `CJM` symbol.

On an upstream outage, the service preserves the original observation timestamp and returns `CACHED` or `DEGRADED`; it never fabricates prices or advances timestamps. Optional evidence sources may still become `UNAVAILABLE` without blocking the eleven-dimensional calculation. The frontend timeout is widened modestly as a transport guard, but normal market endpoints should return from local snapshots in well under one second.

## Verification

- Unit-test symbol aliasing, persisted observed timestamps, degraded-state behavior, and term-structure output.
- Run all Python and Vue tests plus the production frontend build.
- Rebuild the algorithm and frontend containers, clear only strategy prediction cache keys, and verify all four page APIs repeatedly through Nginx.
- Confirm prediction output contains 11 empirical dimensions, 3 weighted cultural references, and the new observed-data model version.
