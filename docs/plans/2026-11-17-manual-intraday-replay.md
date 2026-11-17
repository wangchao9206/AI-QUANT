# Manual intraday replay and private fill journals implementation plan

**Goal:** Let the user manually replay real minute futures candles in the existing web paper-trading workspace, submit orders, save personal reflections per fill, and test the running application through Docker.

**Architecture:** Extend the existing algorithm data archive endpoints and Java paper ledger, reusing authenticated Gateway routing, PostgreSQL tenant isolation, charting, next-bar matching and session persistence. Minute archives are local authorized observations, never generated prices. Freeze replay bars and indicator context in each session; serve only the known cursor prefix. Notes belong to the authenticated author and a specific session/fill, with optimistic revisions.

**Tech stack:** Python/FastAPI, Java 17/Spring/JDBC/Flyway, PostgreSQL, Vue 3/TypeScript/Vitest, existing Docker Compose light mode.

## Product behavior

- Historical replay offers daily and 1/3/5/15-minute periods. Default the new minute workflow to the available glass January 2027 archive and manual orders, one lot.
- Keep daily/live existing sessions compatible; minute replay supports manual actual contracts only, not daily automatic strategies or automatic rolling.
- Reveal completed candles only; queued orders match from the next candle, using existing adverse slippage/participation/fees. Show datetime labels, real execution markers, MA20 and known prior daily MACD context.
- Support single-step, five-step and pause/play. Reloading the page resumes the persisted cursor and account. Optional fixed stop defaults to ten ticks for new minute sessions; daily close liquidation defaults on. No automatic reversal or profit target.
- Every fill has a personal journal action. A selected fill shows timestamp, action, price, quantity and costs above an editable reflection. Save explicitly, retain local dirty text through replay refreshes, and reject stale revisions rather than overwrite concurrent edits. Another user/tenant cannot read or edit this author's note.

## Tasks

1. Add `data/intraday_replay.py`, archive publisher and meaningful Python tests. Publish the frozen real FG701 minute data to ignored `data/history/intraday-replay/`. Validate complete aggregation buckets, trading dates, chronology, OHLCV, source digest, and causal daily context. Internal history/chart/catalog endpoints accept explicit period; no future replay data goes through public chart routes.
2. Add backward-compatible request/session period fields and simulation client methods. Add a Flyway migration for session configuration/context and author-private fill notes with tenant/session/fill foreign keys and FORCE RLS. Extend creation, cursor/chart handling, fixed manual stop and end-of-day liquidation; keep old daily paths intact. Add note read/save endpoints and tests for persistence, revisions and boundaries.
3. Extend the existing Vue workspace with period/catalog selection, datetime chart markers, minute replay controls, and a focused fill note editor. Reuse current visual tokens. Add component/API tests for minute data selection, exact candle marker placement, journal load/save/race/error flows, and account switching.
4. Run Python, targeted frontend/Java tests, production type/build checks and disposable PostgreSQL integration tests. Inspect browser rendering on desktop and mobile; check next-bar fills, pause/resume, saved journals after refresh, and no future candles. Use temporary QA records/identity only, preserving user's records.
5. Build and launch the current project via existing Docker configuration and project name `ai-quant`. Retain all existing environment values and named volumes. Check healthy services, accessible frontend, protected API, and persisted archives/notes. Deliver exact local URL and account bootstrap status without exposing secrets.

## Deployment constraints

The 2026-11-06 handoff's historical request not to deploy is superseded by this user's explicit request to start Docker. Existing production data, if present, must be backed up before migrations; never reset admin credentials or remove data volumes. Prefer full existing service compatibility, using supported static/light mode. If image/network issues occur, fix them or use a documented safe local fallback; do not declare deployment successful before reaching the web application.
