# Domestic Futures Market Implementation Plan

> **For Codex:** Execute this plan task-by-task and verify each checkpoint before
> moving on.

**Goal:** Serve every currently listed domestic futures product and contract from
real observed data through the existing Python, Spring and Vue stack.

**Architecture:** Add a durable dynamic catalog to the background market collector,
publish it through FastAPI and Spring, then make the Vue store and market view
catalog-driven. Keep history lazy and quotes batched for predictable load.

**Tech Stack:** Python 3.12, FastAPI, httpx, Spring Boot 3.5, PostgreSQL, Redis,
Vue 3, Pinia, TypeScript, Docker Compose.

---

### Task 1: Dynamic provider catalog

1. Add failing parser and cache tests for five exchanges and real contract symbols.
2. Implement product-directory and contract-list parsers.
3. Persist catalog state with market snapshots.
4. Verify Python tests.

### Task 2: Generalized background market collection

1. Add a failing CFFEX quote-format test.
2. Parse both commodity and financial-futures quote layouts.
3. Batch all catalog quote symbols and keep history lazy.
4. Generalize maturity parsing and term-structure lookup.

### Task 3: Catalog APIs and evidence isolation

1. Add FastAPI catalog response models and endpoint tests.
2. Remove the CJ-only term-structure guard.
3. Pass product identity into news/rule evidence collectors.
4. Ensure unrelated product evidence becomes `UNAVAILABLE`, never reused.

### Task 4: Spring market-service passthrough

1. Add catalog response records and client method.
2. Add `/api/v1/market/instruments` to the controller and service.
3. Expand watched-symbol capacity without blocking request paths.
4. Run backend tests.

### Task 5: Vue all-market selector

1. Add catalog types/API/store state and tests.
2. Build a searchable exchange-grouped selector.
3. Make term structure optional so one missing curve cannot blank the page.
4. Run unit tests and production build.

### Task 6: Docker acceptance

1. Rebuild affected containers.
2. Verify catalog exchange/product/contract counts and several representative APIs.
3. Verify eleven empirical slots and three cultural references on non-CJ products.
4. Run concurrent request checks and inspect container health.

