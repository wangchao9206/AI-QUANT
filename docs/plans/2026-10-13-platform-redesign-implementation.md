# AI-QUANT Platform Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a production-oriented Vue 3 and Spring Cloud Alibaba platform around the existing Python eleven-dimension quant engine.

**Architecture:** A Vue SPA calls Spring Cloud Gateway. Market and strategy services own business APIs, Redis/PostgreSQL persistence, and resilient calls to a stateless Python FastAPI algorithm adapter. Nacos, Sentinel, RocketMQ, observability, and Docker Compose provide the operational baseline.

**Tech Stack:** Vue 3, TypeScript, Vite, Pinia, Vue Router, Vitest, Java 17, Spring Boot 3.5.x, Spring Cloud 2025.0.x, Spring Cloud Alibaba 2025.0.x, PostgreSQL, Redis, RocketMQ, FastAPI, pytest, Docker Compose.

---

### Task 1: Establish the repository structure and contracts

**Files:**
- Create: `frontend/package.json`
- Create: `backend/pom.xml`
- Create: `algorithm_service/app.py`
- Create: `contracts/openapi.yaml`
- Modify: `.gitignore`

**Steps:**
1. Add the frontend, backend multi-module, algorithm adapter, infrastructure, and contracts directories.
2. Define one canonical prediction response with data freshness, timestamp, signal, risk levels, dimensions, and trace ID.
3. Add smoke tests that import the Python adapter and validate the response schema.
4. Run `python -m pytest tests -q`; expect all tests to pass.

### Task 2: Expose the existing algorithm as a stateless service

**Files:**
- Create: `algorithm_service/app.py`
- Create: `algorithm_service/models.py`
- Create: `tests/test_algorithm_api.py`
- Modify: `requirements.txt`

**Steps:**
1. Write failing tests for health and prediction endpoints using an in-process ASGI client.
2. Implement `/health` and `/api/v1/predictions/{symbol}` with strict validation, request IDs, bounded execution, and consistent error bodies.
3. Reuse `FuturesDataFeed` and `HolisticFusionEngine`; do not copy algorithm logic.
4. Run `python -m pytest tests/test_algorithm_api.py -q`; expect pass.

### Task 3: Build the Spring Cloud parent and gateway

**Files:**
- Create: `backend/pom.xml`
- Create: `backend/gateway-service/pom.xml`
- Create: `backend/gateway-service/src/main/java/com/aiquant/gateway/GatewayApplication.java`
- Create: `backend/gateway-service/src/main/resources/application.yml`
- Test: `backend/gateway-service/src/test/java/com/aiquant/gateway/GatewayApplicationTests.java`

**Steps:**
1. Add Java 17, Spring Boot 3.5.x, Spring Cloud 2025.0.x, and Alibaba 2025.0.x BOMs.
2. Add Gateway WebFlux, Nacos discovery, Sentinel, Actuator, and Micrometer dependencies.
3. Configure explicit market and strategy routes, CORS, request ID propagation, timeouts, and health probes.
4. Run `mvn -f backend/pom.xml -pl gateway-service test`; expect pass without external infrastructure.

### Task 4: Implement Market Service with cache-aside reads

**Files:**
- Create: `backend/market-service/**`
- Create: `backend/market-service/src/main/resources/db/migration/V1__market_schema.sql`
- Test: `backend/market-service/src/test/**`

**Steps:**
1. Write controller and service tests for current quote, history, and term structure.
2. Add validated DTOs and explicit `FRESH`, `CACHED`, and `DEGRADED` states.
3. Implement PostgreSQL persistence with Flyway and indexed timestamp/symbol queries.
4. Implement Redis cache-aside reads with TTL jitter and stale snapshot fallback.
5. Run module tests with Testcontainers when Docker is available; otherwise run mocked repository tests.

### Task 5: Implement Strategy Service and resilient algorithm calls

**Files:**
- Create: `backend/strategy-service/**`
- Create: `backend/strategy-service/src/main/resources/db/migration/V1__strategy_schema.sql`
- Test: `backend/strategy-service/src/test/**`

**Steps:**
1. Write contract tests for the Python response and degraded response.
2. Implement a WebClient adapter with connection/read timeouts, bounded retry, circuit breaker, and bulkhead.
3. Coalesce concurrent calculations per symbol and cache successful decisions.
4. Persist model version, input timestamp, result, freshness, and trace ID.
5. Run `mvn -f backend/pom.xml -pl strategy-service test`; expect pass.

### Task 6: Build the Vue design system and application shell

**Files:**
- Create: `frontend/src/styles/tokens.css`
- Create: `frontend/src/styles/base.css`
- Create: `frontend/src/components/**`
- Create: `frontend/src/layouts/AppShell.vue`
- Test: `frontend/src/**/*.spec.ts`

**Steps:**
1. Write component tests for navigation, freshness badges, loading, empty, and error states.
2. Implement semantic tokens for color, type, spacing, radius, elevation, and motion.
3. Build responsive sidebar/bottom navigation, skip link, focus states, and reduced-motion behavior.
4. Run `npm --prefix frontend test`; expect pass.

### Task 7: Implement the four product pages

**Files:**
- Create: `frontend/src/views/OverviewView.vue`
- Create: `frontend/src/views/MarketView.vue`
- Create: `frontend/src/views/StrategyView.vue`
- Create: `frontend/src/views/SystemView.vue`
- Create: `frontend/src/stores/market.ts`
- Create: `frontend/src/services/api.ts`

**Steps:**
1. Implement the overview with price, signal, risk levels, sparkline, resonance, and dimension summary.
2. Implement market, strategy, and system views with responsive layouts and truthful timestamps.
3. Add skeleton, empty, stale, error, and retry states for every asynchronous region.
4. Add mock fallback only in development; never label mock data as live.
5. Run tests and `npm --prefix frontend run build`; expect success.

### Task 8: Add infrastructure and production safeguards

**Files:**
- Create: `infrastructure/docker-compose.yml`
- Create: `infrastructure/.env.example`
- Create: `backend/**/Dockerfile`
- Create: `frontend/Dockerfile`
- Create: `algorithm_service/Dockerfile`
- Create: `docs/operations.md`

**Steps:**
1. Define PostgreSQL, Redis, Nacos, RocketMQ, services, and health checks with pinned images.
2. Add non-root containers, resource limits, restart policies, and secrets-through-environment configuration.
3. Document local startup, production overrides, backup, recovery, and degradation behavior.
4. Validate Compose configuration with `docker compose config`.

### Task 9: Verify behavior, visuals, and concurrency

**Files:**
- Create: `tests/load/k6-smoke.js`
- Create: `docs/verification.md`

**Steps:**
1. Run the full Python, Maven, and frontend test suites.
2. Start the stack and verify health, quote, prediction, and SPA navigation endpoints.
3. Capture desktop and mobile screenshots; fix overflow, contrast, focus, and loading issues before delivery.
4. Run a stepped load test and record p50, p95, error rate, throughput, CPU, and memory.
5. Confirm algorithm timeout, Redis outage, and stale-data fallback behavior.

