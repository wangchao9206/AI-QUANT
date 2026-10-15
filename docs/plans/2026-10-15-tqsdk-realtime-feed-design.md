# TqSdk Real-time Feed Design

## Requirements

The system must receive authenticated, push-based domestic futures quotes, cover
all supported exchanges, keep the current Java/Python/Vue boundaries, survive
provider disconnects, and never label public polling as live trading data. The
deployment must continue to run entirely in Docker and must not expose or log
credentials.

## Architecture

`AuthenticatedMarketFeed` wraps the existing public collector. Its dedicated
TqSdk worker owns one `TqApi` instance and is the only thread that calls
`wait_update`. It discovers unexpired futures with `query_quotes`, subscribes to
all current contracts and continuous contracts, and lazily adds daily K lines
for explicitly watched symbols. It copies updates into locked plain-Python dictionaries. Existing FastAPI endpoints
read those dictionaries without network I/O. Java continues to persist and
cache snapshots through its current ingestion job.

Canonical API symbols remain `RBM` and `RB2701`; the adapter translates these to
TqSdk symbols such as `KQ.m@SHFE.rb` and `SHFE.rb2701`. INE products are grouped
with SHFE in the existing five-group UI while retaining their provider symbol.

## Failure and trust semantics

TqSdk quotes are `FRESH` only when their exchange timestamp is within the live
freshness window. Outside that window they become `CACHED`. Missing credentials,
authentication failures and disconnects expose the public/cached fallback only
as `DEGRADED`, with its real source and timestamp preserved. Credentials are
never returned by an endpoint or written to logs.

## Operations

The provider is selected by `MARKET_DATA_PROVIDER=tqsdk`. The local ignored
`.env` supplies `TQSDK_USERNAME` and `TQSDK_PASSWORD`. A provider-status endpoint
reports configured provider, connection state, last event time and fallback
state without sensitive fields. The frontend uses the catalog/quote source and
status already present, so no simulated display mode is added.
