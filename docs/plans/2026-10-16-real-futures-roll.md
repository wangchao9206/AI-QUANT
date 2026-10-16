# Real Futures Roll Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task.

**Goal:** Replace theoretical continuous-contract roll assumptions with auditable TqSdk dominant-contract mappings and executable old/new contract fills.

**Architecture:** A dedicated TqSdk backtest data provider persists real daily dominant mappings, tradable-leg prices, and contract specifications. The backtester consumes explicit roll events and uses an integer-lot execution ledger; the API and Vue UI expose the evidence and limitations.

**Tech Stack:** Python 3.12, TqSdk 3.10.2, FastAPI/Pydantic, pytest, Vue 3/TypeScript/Vitest, Docker Compose.

---

### Task 1: Define the roll data contract with failing tests

**Files:**
- Create: `data/tqsdk_backtest.py`
- Modify: `data/data_feed.py`
- Create: `tests/test_tqsdk_backtest.py`

1. Add tests for Beijing trading-date alignment, dominant-symbol changes, real two-leg prices, and missing-leg rejection.
2. Run `pytest tests/test_tqsdk_backtest.py -q` and confirm failure.
3. Add `contract_symbol`, `FuturesContractSpec`, `RollEvent`, and cached dataset serialization.
4. Run the focused test and confirm pass.

### Task 2: Implement the realistic execution ledger with failing tests

**Files:**
- Modify: `backtesting/backtester.py`
- Modify: `tests/test_backtester.py`

1. Add tests proving integer-lot sizing, tick-based slippage, separate open/close costs, no instant PnL from the price gap, same-day exit without redundant reopen, and margin-limited resizing.
2. Run `pytest tests/test_backtester.py -q` and confirm failure.
3. Replace percentage-notional fills with lot/multiplier accounting and explicit `RollEvent` handling.
4. Run focused tests and confirm pass.

### Task 3: Connect strict real data to the API

**Files:**
- Modify: `algorithm_service/app.py`
- Modify: `algorithm_service/models.py`
- Modify: `tests/test_algorithm_api.py`

1. Add API tests for provider-unavailable errors and roll audit fields.
2. Resolve the TqSdk main symbol from the live catalog, load the cached real dataset, filter bars and events by date, and pass specs/events to the backtester.
3. Never fall back to synthetic roll events when real mapping or either leg is unavailable.
4. Run `pytest tests/test_algorithm_api.py -q`.

### Task 4: Expose execution evidence in Vue

**Files:**
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/views/BacktestView.vue`
- Modify: `frontend/src/views/BacktestView.spec.ts`

1. Add typed fields for contract, lots, commission, slippage, roll gap and model status.
2. Replace the disabled “unavailable” toggle with an automatically enabled real-roll indicator.
3. Show roll costs and price gap separately and include contract/lots in trade records.
4. Run `npm test -- --run` and `npm run build`.

### Task 5: Verify and deploy

**Files:**
- Modify: `docs/operations.md`

1. Run the Python suite and static compilation.
2. Build the algorithm-service and frontend images.
3. Start the stack and confirm all health checks.
4. POST a CJ backtest covering known roll dates and verify returned `ROLL_LONG`/`ROLL_SHORT` records contain two real contracts and prices.
5. Confirm an unconfigured provider fails explicitly instead of producing a theoretical roll result.

