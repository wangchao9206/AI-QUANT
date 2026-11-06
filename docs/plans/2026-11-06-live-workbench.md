# Live Workbench Implementation Plan

**Goal:** Add a main-system live market observation page with real small-period candlesticks, observed depth, tick-derived tape and a transparent depth radar.

**Architecture:** Reuse the single TqSdk worker for bounded, on-demand intraday serials; HTTP threads only read copies. Proxy through existing market-service routes and market.read authorization. Add /live to the validated menu catalog through an additive identity migration, without changing existing custom role permissions. Use a dark, dense chart workspace within the existing main shell.

**Tech Stack:** Python/FastAPI/TqSdk, Spring Boot, PostgreSQL/Flyway, Vue 3/TypeScript, existing SVG TongdaxinChart.

## Decisions

- Direct provider serials at 15/30/60/180/300/900 seconds preserve actual OHLCV and session gaps. Frontend tick aggregation would miss history and depend on browser uptime; embedding the paper-trading workflow would couple looking at markets to an account and order state. Implement direct serials and a separate read-only page.
- Radar measures visible bid/ask imbalance, spread, recent tick-volume direction estimates and observed large tick increments. It does not claim order-by-order Level 2, true aggressor flags or identified capital flows. Missing levels remain missing; stale/paused/failed data suppresses active alerts.
- Small bars and depth refresh independently, avoid overlapping requests, reject stale responses on instrument/period changes, stop on unmount and pause in background tabs. Display separate source times/statuses and explicit refresh errors. Preserve viewport when bars append.
- Use market.read for entry and APIs. Global menu whitelist gains /live -> market, with a new seeded menu. No admin modules added to the main navigation.

## Tasks

1. Add data/intraday_feed.py with strict observed OHLCV conversion, capped subscriptions, worker-only SDK calls, reconnect recovery and freshness metadata. Integrate into data/tqsdk_feed.py. Test malformed bars, periods, timestamps, capacity, retries and same-bar updates.
2. Add FastAPI /api/v1/market/{symbol}/intraday (period and limit validation, explicit warming/unavailable). Extend market-service DTO/client/service/controller; cover proxy validation and 503 behavior.
3. Add frontend live service, pure radar calculations and LiveView. Include exchange/product/real-contract selectors, six periods, chart, depth ladder, tape, measurement labels, polling/pause and safe failure states. Test null/stale data, direction calculations, races, lifecycle and period changes.
4. Add route, main menu, market.read route mapping and identity V3 migration. Update existing menu assertions and docs; verify identity/menu integration and frontend navigation.
5. Run relevant Python, Java and frontend tests; typecheck/build; check desktop/mobile UI. Back up and deploy changed services to the existing ai-quant project, preserve live admin password, validate actual primary data without production test users.

Provider reference: [TqSdk market data](https://doc.shinnytech.com/tqsdk/latest/usage/mddatas.html), supports direct intraday serial subscriptions; only the existing SDK thread may call get_kline_serial/wait_update.

## Completion

Implemented, verified and deployed to the existing ai-quant project. See [behavior](../live-workbench.md) and [deployment evidence](../deployment-live-2026-11-06.md). Real primary data confirmed 400 bars at each of the six periods, observed five-level depth and 80 tick-volume increments; closed-session timestamps remain visibly cached.
