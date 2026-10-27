# Paper trading repair and strategy execution

**Goal:** Restore reliable historical trading and provide selectable, auditable strategy simulation in historical and live modes.

**User decision:** Both historical and live strategy execution are required. Preserve manual mode and existing experiments.

**Architecture:** Python evaluates deterministic daily signals; Java remains the only writer of accounts, orders, fills and risk state. Historical signals use frozen observations no later than the replay cursor and execute on the next bar. Live signals use completed observations and execute only with a valid live quote. HTTP computations happen outside ledger transactions; version checks and signal-time uniqueness prevent duplicate decisions.

**Design choices:** Browser-only automation loses state and cannot enforce deduplication, so use server-side execution on advance/refresh. Share technical entry/exit rules with the backtester. Freeze the selected strategy, lot count and ATR protection settings per account. New strategy accounts show their signal evidence and net performance; original accounts remain manual.

## Tasks

1. Diagnose historical creation/order/advance failures using read-only account data and isolated regressions. A production audit-account/order attempt was rejected by automatic review; do not retry that side effect without explicit user approval.
2. Extract shared daily signal evaluation into `backtesting/strategy_signals.py`; add bounded, timezone-aware internal strategy and live-context APIs and tests. Keep signal bars separate from executable delivery bars.
3. Add a forward Flyway migration for frozen strategy settings, signal bars/decisions and performance state. Extend `SimulationDataClient` and `PaperTradingService` with version-checked strategy execution, daily deduplication, and closed/stale live refresh without fictitious fills.
4. Extend the existing paper screen with strategy selection, fixed lots/ATR settings, execution status, signal history and performance comparison. Keep the established design and test selection, data failures, and account switching.
5. Run Python, Java and frontend tests, build deployable artifacts, and validate UI with mocked browser requests or an isolated test environment. Apply the local repair when verification passes; user-owned ledger mutations require the explicit approval described above.

## Verification requirements

- Future bars and uncompleted live daily bars cannot influence a decision.
- Duplicate refreshes cannot submit multiple strategy orders for one signal time.
- Unknown strategies and invalid risk settings fail validation.
- Historical order creation and next-bar execution are verified through the actual service in isolation.
- Live creation does not require a historical replay archive; closed or stale quotes never fill orders.
- Historical and live modes show the chosen strategy, reason, parameters and fees; no performance claims are fabricated.

## Outcome

Implemented and applied to the local stack. Python 362 tests and frontend 183 tests pass. Java unit tests plus six real disposable-PostgreSQL integration scenarios pass; Linux images build successfully. Real-browser mocked interaction checks cover historical/live strategy selection, uncertain-order retries without randomUUID, closed-market refresh and mobile layout. Read-only checks on the real site confirm existing accounts and all seven strategy choices; no audit orders were written to user accounts after the automatic-review rejection. V2/V3 forward migrations preserve existing accounts and retain delivery identity in frozen risk bars. See `docs/verification.md` and `docs/operations.md` for evidence and operating limits.
