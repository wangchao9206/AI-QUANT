# Options Depth and Background Monitoring Implementation Plan

**Goal:** Show the selected futures contract's real options depth in /live and run configurable futures/options monitors on the server, with durable tenant-scoped trigger history even when the browser is closed.

**Architecture:** Reuse the single TqSdk worker for whitelisted options depth/ticks and shared chart serials. Add a pure, versioned Python signal evaluator behind a shared-secret internal API. Persist monitor definitions, evaluator state, leases, configuration audit and deduplicated events in market-service PostgreSQL. Market-service schedules bounded background workers and checks the creator's current tenant/account permissions on every evaluation. Reuse signed Gateway identities and restricted tenant transactions for management APIs, with FORCE RLS on private monitor tables only.

**Tech Stack:** Python/FastAPI/TqSdk, Spring/JDBC/scheduling, PostgreSQL/Flyway/RLS, Vue/TypeScript.

## User decisions

- Background monitoring continues after closing the page and saves trigger records (explicitly selected).
- In-app configuration/status/history; no external email/chat notifications or trading execution requested.

## Semantics

- Match options using the provider's exact underlying delivery contract. Resolve continuous futures from observed underlying metadata; never match a different maturity just because the product root is similar. Pin monitors created from a continuous alias to the resolved delivery contract and show that binding.
- Closed candles (successor observed) drive MA5/10/20/60/180 volume breakouts, Bollinger/Donchian/Keltner channels, volume spikes, ATR displacement, MACD(12,26,9) crosses and confirmed pivot DIF divergences. Default pivot confirmation needs two later closed candles; record confirmation time and both pivot evidences.
- Live rules cover rolling 60-second changes (default >10% up/down), large classified tick-volume increments, and visible depth imbalance. Big buy/sell means estimated tick direction, not identified orders/actors. Defaults and thresholds are editable and documented.
- Fresh quotes and matching chart watermarks are required. No alerts during stale/closed/disconnected data, first startup, historical warming or replay of old ticks. Require an observed 60-second baseline; gaps restart the window. Store evidence, rule/algorithm version, source/confirmation times and dedup keys, with cooldowns and persisted watermarks.
- Per-tenant 20 enabled monitors, global 32 enabled; bounded SDK subscriptions and worker pool, explicit capacity errors. Config changes use optimistic versions; leases prevent duplicate workers, and a stale evaluation cannot persist after pause/edit. Cross-tenant lookups fail and background authorization revocation suspends monitoring.

## Steps

1. Extend options feed with a validated contract index, bounded worker-owned live depth/tick subscriptions and metadata linkage. Expose linked catalog/depth/chart endpoints under existing options permissions.
2. Add pure Python signal rules and internal validate/catalog/evaluate endpoints, then tests for each requested signal, no-lookahead divergence, gaps, stale data, startup, dedup/cooldown and zero/invalid prices.
3. Add identity internal background authorization check; add market V2 private tables and RLS; implement signed monitor request boundary, CRUD, events/ack, config audit, leases, scheduler and current authorization checks. Test real PostgreSQL tenant isolation, version races and durable dedup.
4. Add exact-linked option selectors/depth/chart in /live and a reusable background monitoring panel for futures and options: rule settings, create/edit/pause, status/time, searchable paginated events and evidence details. Keep existing watch/chart features intact.
5. Run focused/full relevant regression, build/typecheck and browser QA. Back up DB and images, deploy affected services to ai-quant, verify actual option data and persistent monitor operations using isolated test identities, preserve the live administrator password and original business data.

References: [TqSdk market data](https://doc.shinnytech.com/tqsdk/latest/usage/mddatas.html), [underlying contract metadata](https://doc.shinnytech.com/tqsdk/latest/quickstart.html).

## Verification progress

- Steps 1–4 implemented. Python rule/provider regression, PostgreSQL RLS/lease/transaction tests, identity/Gateway tests and 337 frontend tests passed before deployment preparation. Additional irregular-sampling minute-window regression added during final review.
- Real HTTP integration against disposable PostgreSQL passed: signed identity, delivery pinning, events without browser requests, pause/version race, acknowledgement, option separation, tenant isolation and authorization revocation. Disposable database and HTTP processes removed after checks.
- Production frontend build and desktop/mobile browser QA passed: 23 rules, five MA choices, nine option periods, real-shaped option depth and evidence panel; no whole-page horizontal overflow or browser exceptions. Fixtures were explicitly isolated test data.
- All five steps completed. Production database dump verified (529 archive entries), five prior images preserved with `before-options-monitor-20261106` tags. Five updated services healthy, market V2 FORCE RLS verified, original 17 paper sessions and administrator state preserved. Production static assets match the final build; unauthorized private requests rejected. Actual RB2701-linked SHFE.rb2701C3050 depth (5/5), 71 ticks and 600 minute bars verified; closed-market evaluations returned STALE with no replayed triggers. See [deployment record](../deployment-options-monitor-2026-11-06.md).
