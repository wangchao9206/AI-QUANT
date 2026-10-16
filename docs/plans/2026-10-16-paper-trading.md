# Paper Trading and Historical Replay Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a persistent paper-trading console for live market experiments and deterministic historical manual replay.

**Architecture:** Add a Spring Boot `paper-trading-service` as the sole owner of accounts, orders, fills, positions, and replay clocks. It consumes real market data from the existing Java/Python services and persists transactional state in a dedicated PostgreSQL schema. Vue exposes one trading console for both modes.

**Tech Stack:** Java 17, Spring Boot 3.5, Spring Cloud Alibaba, JPA/Flyway, PostgreSQL 17, Vue 3, TypeScript, Docker Compose.

---

### Task 1: Freeze the data contract

**Files:**
- Modify: `algorithm_service/app.py`
- Modify: `algorithm_service/models.py`
- Test: `tests/test_algorithm_api.py`

Add an internal historical replay endpoint returning real contract-tagged bars, roll events and contract specifications. Verify missing real data returns 503.

### Task 2: Create the paper-trading service and schema

**Files:**
- Create: `backend/paper-trading-service/**`
- Modify: `backend/pom.xml`

Create Flyway tables for sessions, scenario bars, orders, fills and positions. Add indexes for session timelines and open-order scans, unique idempotency constraints and numeric/check constraints.

### Task 3: Implement deterministic matching

**Files:**
- Create: `backend/paper-trading-service/src/main/java/com/aiquant/paper/service/**`
- Test: `backend/paper-trading-service/src/test/**`

Implement next-bar historical matching, integer lots, tick slippage, fees, margin validation, position netting and conservative limit/stop behavior. Test no look-ahead, duplicate request idempotency and insufficient-margin rejection.

### Task 4: Expose session APIs

**Files:**
- Create: `backend/paper-trading-service/src/main/java/com/aiquant/paper/api/**`

Expose create/list/detail, place/cancel order, advance replay, pause/resume and reset endpoints. Use validated DTOs and stable error responses.

### Task 5: Route and deploy

**Files:**
- Modify: `backend/gateway-service/src/main/resources/application.yml`
- Modify: `infrastructure/docker-compose.yml`
- Modify: `infrastructure/prometheus/prometheus.yml`

Route `/api/v1/paper/**`, add health checks, separate `paper_trading` Flyway schema, resource limits and service dependencies.

### Task 6: Build the Vue trading console

**Files:**
- Create: `frontend/src/views/PaperTradingView.vue`
- Create: `frontend/src/views/PaperTradingView.spec.ts`
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/router.ts`
- Modify: `frontend/src/layouts/AppShell.vue`

Build session setup, replay clock, order ticket, account/position cards, open-order and fill tables. Clearly mark all actions as simulation and show data timestamps.

### Task 7: Verify end to end

Run Python, Maven and frontend test suites; build Compose; create a historical CJ session, submit a pending order, advance one bar and verify one auditable fill and position in PostgreSQL.

