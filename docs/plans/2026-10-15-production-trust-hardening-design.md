# Production Trust Hardening Design

## Objective

Turn the current local lead-pool, historical-data, backtest, and dashboard work into a release candidate whose displayed facts can be traced to observed inputs and whose backtest cannot trade on information unavailable at order time.

## Chosen approach

Keep the existing Vue 3, Spring Cloud Alibaba, and Python service boundaries. Harden the Python API as the single calculation authority, keep the Spring gateway as the only browser-facing API path, and remove presentation-layer synthesis of market data. This is less disruptive than a rewrite and allows the existing interface investment to survive.

## Data truth contract

- Missing OHLCV remains missing. The UI may render a close-only line but must never create candles or volume.
- Historical continuous contracts are identified as continuous contracts; a specific delivery contract is never silently mapped to a continuous series.
- Freshness is derived from the last observation and current trading/calendar time. Local files are reported as cached, never unconditionally fresh.
- Lead narratives are assembled only from returned dimension evidence. No inventory, order-flow, statistical-significance, news, or probability claim is shown unless that field exists in the source payload.
- Cultural dimensions retain the approved weight but are visibly separated and require an empirical-only comparison in later model validation. They are never described as empirical evidence.

## Backtest execution contract

- A bar may generate a signal only after it closes; the earliest fill is the next bar open.
- Intrabar stops fill at the configured stop price, pessimistically adjusted for gaps and slippage.
- A forced final close must be reflected in the final equity point and all downstream metrics.
- Synthetic roll-yield profiles are removed. Roll costs are only applied when real contract transition data exists; otherwise the result explicitly reports roll modeling as unavailable.
- Requests use bounded, validated parameters and a known strategy enum.

## Reliability and security

- Backtests run behind a bounded semaphore and return 429 when capacity is exhausted instead of exhausting the worker pool.
- The browser reaches backtest and data APIs through Spring Gateway, not a direct Python proxy.
- API exceptions return stable public messages with trace IDs; internal exception text remains in server logs.
- Historical cache receives a dedicated writable Docker volume while application code remains read-only.
- Nginx adds baseline security headers and keeps a single API routing policy.

## Verification gates

Release requires Python unit/API tests, Vue component tests, a production frontend build, Docker Compose configuration validation, regression tests proving next-bar execution and no fabricated chart data, plus API tests for invalid parameters, contract identity, freshness, lead generation, and concurrency rejection.

