# Live Calendar Periods and Moving Averages Implementation Plan

**Goal:** Extend the deployed live workbench with daily, calendar-week and calendar-month candles plus MA5/10/20/60/180.

**Architecture:** Subscribe once to up to 8000 provider daily bars per long-period symbol; compute calendar aggregates on the existing SDK worker, and expose snapshots through the existing market.read boundary. Retain all short-period requests. Compute full-window moving averages from all loaded candles before viewport slicing.

**Tech Stack:** TqSdk/Python, Spring market-service, Vue/TypeScript/SVG.

## Decisions

- Use provider daily trading-date labels in Asia/Shanghai, group Monday–Sunday and calendar months. Fixed second durations cannot represent calendar months. Add optional period=DAY/WEEK/MONTH to the current endpoint; preserve seconds for intraday requests.
- Reuse one daily serial for daily/weekly/monthly requests, rebuild caches on updates, preserve the pending final candle. Exclude a truncated first aggregation bucket unless source history starts at provider index zero. Never fill missing trading days.
- MA values require N real closes, use the current partial final candle as an explicitly provisional close, and display a gap/— before N samples. Draw all five lines with distinct labels/colors and per-line visibility controls. Include visible MA values in chart price scaling.

## Tasks

1. Extend data/intraday_feed.py with shared daily subscriptions, calendar aggregation and period metadata. Test month/year/leap boundaries, holiday gaps, OHLCV/OI, partial boundaries and updates to current periods.
2. Extend FastAPI and market-service validation/proxy/DTO while keeping legacy seconds paths compatible. Verify valid calendar periods and 400/503 behavior.
3. Extend live.ts/LiveView to nine periods, switch long periods to date labels and explain available historical length. Refactor chart MA calculations into a tested rolling-window utility, render configurable five-line overlays with gaps and correct scale.
4. Run relevant Python/Java/frontend regression, typecheck/build, browser-check real chart layouts; deploy to the same ai-quant project with rollback images and verify actual daily/weekly/monthly OHLCV without changing live accounts.

## Completion

Implemented and deployed. Final frontend resources, private calendar data and unauthenticated API denial verified. See [deployment evidence](../deployment-calendar-ma-2026-11-06.md). RBM currently has 131 provider-observed monthly bars, so its monthly MA180 is explicitly unavailable; daily and weekly MA180 are supported by sufficient observations.
