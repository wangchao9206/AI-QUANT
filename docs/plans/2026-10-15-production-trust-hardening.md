# Production Trust Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Produce a locally verifiable release candidate that never fabricates market evidence, removes backtest look-ahead bias, validates requests, and protects the service from unbounded heavy work.

**Architecture:** Python remains the calculation and market-data authority, Spring Cloud Gateway remains the browser ingress, and Vue renders explicit data-quality states. Heavy synchronous backtests are bounded at the API boundary; truthful metadata travels with calculation results.

**Tech Stack:** Python 3, FastAPI, Pydantic, pytest, Vue 3, TypeScript, Vitest, Nginx, Spring Cloud Gateway, Docker Compose.

---

### Task 1: Lock down the API contracts

**Files:**
- Modify: `algorithm_service/models.py`
- Test: `tests/test_algorithm_api.py`

1. Add failing tests for unknown strategies, invalid dates, negative capital/costs, unsafe leverage, and invalid position size.
2. Add enums and Pydantic field/model validators with conservative bounds.
3. Verify invalid requests return 422 without entering the backtester.

### Task 2: Make lead generation evidence-only

**Files:**
- Modify: `algorithm_service/app.py`
- Test: `tests/test_algorithm_api.py`

1. Add a test that executes the real lead classifier with an S-grade prediction.
2. Replace fixed statistical, inventory, order-flow, and news prose with summaries derived from returned dimensions.
3. Count directional dimensions explicitly, align direction with composite score, remove the catch-all cultural lead, and derive aggregate data status from inputs.

### Task 3: Remove look-ahead and fictional rolls

**Files:**
- Modify: `backtesting/backtester.py`
- Test: `tests/test_backtester.py`

1. Add deterministic tests proving a close-generated signal fills no earlier than the next open.
2. Queue entry/reversal signals and execute at the following open.
3. Use stop prices with pessimistic gap handling.
4. Disable synthetic calendar rolls unless real roll events are supplied.
5. Append or replace the final equity point after forced liquidation.

### Task 4: Enforce truthful historical data semantics

**Files:**
- Modify: `data/history_manager.py`
- Modify: `algorithm_service/app.py`
- Test: `tests/test_algorithm_api.py`

1. Validate timestamp ordering and OHLC invariants when loading history.
2. Reject specific-contract requests when only continuous history is available.
3. Report local history as cached with its real update timestamp.
4. Expose source, series type, validation counts, and last observation metadata.

### Task 5: Protect heavy endpoints and unify ingress

**Files:**
- Modify: `algorithm_service/app.py`
- Modify: `frontend/nginx.conf`
- Modify: `infrastructure/docker-compose.yml`
- Modify: `backend/gateway-service/src/main/resources/application.yml`
- Test: `tests/test_algorithm_api.py`

1. Add a bounded backtest capacity guard and 429 response.
2. Route all browser API traffic through the gateway.
3. Add a writable history-cache volume and worker/concurrency configuration.
4. Add security headers and consistent timeouts.

### Task 6: Remove UI misinformation

**Files:**
- Modify: `frontend/src/components/TongdaxinChart.vue`
- Modify: `frontend/src/views/BacktestView.vue`
- Modify: `frontend/src/views/LeadsView.vue`
- Modify: `frontend/src/services/api.ts`
- Test: corresponding `*.spec.ts`

1. Add tests that missing OHLCV does not create candles or volume.
2. Replace hard-coded performance claims and dates with API metadata and the current date.
3. Stop automatic backtests on navigation and add explicit methodology/data warnings.
4. Improve chart/button keyboard and ARIA semantics.

### Task 7: Full verification

1. Run `python -m pytest -q`.
2. Run `npm test -- --run` in `frontend`.
3. Run `npm run build` in `frontend`.
4. Run Docker Compose config validation and build the affected images.
5. Smoke-test health, provider status, history, leads, invalid backtest, and valid backtest through port 18080.
6. Record remaining external prerequisites such as valid TqSdk credentials and exchange-specific fee/multiplier reference data.

