# Domestic Options Implementation Plan

**Goal:** Add domestic commodity and financial index option quotes, strike chains and transparent risk analysis to the existing console.

**Architecture:** Keep provider option identifiers intact in a separate catalog. Use the existing TqSdk worker for lazy metadata discovery and bounded chain subscriptions; request threads only read copied snapshots. Never route options through futures symbol parsing, fallback pricing, simulation or backtesting. Compute Black-76 references for futures underlyings and BSM references for index underlyings, explicitly identifying American-option European approximations and user-supplied rate/dividend assumptions.

**Tech Stack:** Python/FastAPI, TqSdk 3.10.2, Vue 3/TypeScript, existing Gateway.

## Design decisions

- Recommended: independent `/options` workspace and `/api/v1/options` API sharing the primary connection. This preserves option type, strike, actual expiry, actual underlying and exercise style without overloading futures contracts.
- Alternative: add options to the futures catalog. Rejected because futures symbol normalization, margin and rollover logic are incompatible.
- Alternative: separate options connection/service. Unnecessary for this research-only first release and would duplicate authenticated connections.
- Catalog groups by exchange, actual underlying and exact expiry. Index option underlyings remain indices; no substitution of corresponding futures.
- Provider-unavailable, warming, stale, one-sided/crossed books and unsupported metadata are visible states. Missing values remain null. No generated demonstration prices.
- Risk analysis includes IV, Delta/Gamma/Theta/Vega, intrinsic/time value, spread and single-leg expiry payoff for a chosen quantity and side. Scenario curves are mathematical calculations, exclude fees and execution, and do not represent market forecasts.

## Implementation sequence

1. Add `data/options_feed.py` for lazy catalog discovery, bounded batch quote subscriptions, immutable snapshots, reconnect/error isolation. Integrate one `poll()` call into the existing SDK owner loop in `data/tqsdk_feed.py`.
2. Add `algorithm_service/options.py` with validated APIs, model pricing, IV inversion, documented Greek units and expiry payoff. Include router in `algorithm_service/app.py` and route prefix through Gateway.
3. Add `frontend/src/types/options.ts`, `frontend/src/services/options.ts`, and `frontend/src/views/OptionsView.vue`. Add navigation and route; show mirrored strike chains, data states, model assumptions, Greek explanations and payoff chart. Guard against obsolete asynchronous responses.
4. Add meaningful Python tests for observed-only ingestion, no-data paths, underlying classification, expiry/model bounds, finite-difference Greeks and payoff risk. Add Vue tests for selection, empty/error/stale states and request races. Verify targeted regression suites and production build.
5. Document operation, model limitations and API parameters. Record actual verification results without claiming live market validation unless credentials and real provider responses are available.

## Verification commands

`python -m pytest tests/test_options.py tests/test_tqsdk_feed.py -q`

`npm test -- --run src/views/OptionsView.spec.ts src/router.spec.ts src/layouts/AppShell.spec.ts`

`npm run build`

## Primary provider references

- https://doc.shinnytech.com/tqsdk/latest/reference/tqsdk.api.html (query_quotes, query_symbol_info, get_quote_list)
- https://doc.shinnytech.com/tqsdk/latest/reference/tqsdk.objs.html (Quote metadata, exercise_type A/E)

No real trading, option backtesting, early-exercise valuation or brokerage margin formulas are included in this phase.
