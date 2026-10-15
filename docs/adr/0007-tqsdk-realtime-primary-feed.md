# ADR 0007: TqSdk as the authenticated real-time primary feed

## Status

Accepted for implementation on 2026-10-15.

## Context

The current Sina integration provides real observed public quotes through HTTP
polling. It is useful as a transparent fallback, but it is not an authenticated,
push-based production market-data session and must not be presented as such.
The application needs all domestic futures products, continuous updates, one
Docker deployment, and bounded load under many browser requests.

## Decision

Use one long-lived, data-only TqSdk session inside the Python market collector as
the primary real-time source. The session owns all TqSdk objects in one worker
thread, subscribes to requested contracts and continuous contracts, and copies
immutable snapshots into the existing thread-safe market feed. HTTP requests,
Java services and browsers never create TqSdk sessions.

Credentials are injected only through `TQSDK_USERNAME` and `TQSDK_PASSWORD` in
the ignored local `.env`. No trading account is configured and this decision
does not authorize order placement. The public Sina collector continues in a
separate fallback path. A fallback quote is always labelled `DEGRADED` when the
configured primary source is TqSdk.

## Consequences

- Exchange timestamps and last-trade market snapshots arrive through a push loop.
- A single upstream session serves all internal consumers, preventing connection
  multiplication under high concurrency.
- TqSdk availability and credentials become operational dependencies.
- Without credentials, the stack remains readable through cached/public data but
  explicitly reports that the real-time primary feed is unavailable.
- Production redistribution and account licensing remain the operator's
  responsibility and must be confirmed with the provider.
