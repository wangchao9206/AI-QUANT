# TqSdk Real-time Feed Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make authenticated TqSdk push quotes the primary domestic-futures feed while retaining the public collector as an explicitly degraded fallback.

**Architecture:** Add a provider adapter and an overlay feed selected by environment. One worker owns the TqSdk session and publishes immutable snapshots; existing request and persistence paths remain unchanged.

**Tech Stack:** Python 3.12, TqSdk 3.10.2, FastAPI, Docker Compose, Spring services, Redis, PostgreSQL.

---

### Task 1: Provider translation and quote conversion

**Files:**
- Create: `data/tqsdk_feed.py`
- Create: `tests/test_tqsdk_feed.py`
- Modify: `requirements.txt`

1. Write failing tests for canonical/TqSdk symbol translation and quote conversion.
2. Implement finite-value validation, exchange timestamps and catalog grouping.
3. Pin the provider package and run the new tests.

### Task 2: Long-lived collector and degraded overlay

**Files:**
- Modify: `data/tqsdk_feed.py`
- Modify: `algorithm_service/app.py`
- Modify: `algorithm_service/models.py`
- Test: `tests/test_tqsdk_feed.py`

1. Add a single-owner worker with dynamic subscriptions and bounded reconnect delay.
2. Add an overlay implementing the existing feed methods.
3. Ensure all fallback responses are `DEGRADED` when TqSdk is selected but unavailable.
4. Expose a credential-safe provider status endpoint.

### Task 3: Docker configuration and operational documentation

**Files:**
- Modify: `infrastructure/docker-compose.yml`
- Modify: `infrastructure/.env.example`
- Modify: `README.md`
- Modify: `docs/operations.md`

1. Inject provider selection and optional credentials from the ignored `.env`.
2. Document data-only credentials, startup and verification.
3. Keep the public provider available as fallback, not as real-time primary.

### Task 4: Verification

1. Run all Python tests.
2. Build the algorithm image with pinned TqSdk.
3. Start without credentials and verify honest `DEGRADED` status plus working fallback.
4. If credentials are present locally, verify TqSdk connection and exchange timestamps; otherwise report that credential-dependent acceptance remains pending.
5. Commit and push the batch.
