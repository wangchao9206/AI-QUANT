# Real Eleven-Dimension Analysis Implementation Plan

> Historical plan: its zero-weight cultural-reference decision was superseded by ADR-0005 and the approved afternoon model.

> **For Claude:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task.

**Goal:** Deliver eleven auditable empirical dimensions plus three time-derived cultural references, with no fake fallback data and no cultural influence on trading scores.

**Architecture:** Python concurrently gathers live market, historical, term-structure, weather, news, and trading-rule evidence behind bounded TTL caches. Eleven empirical engines consume only observed evidence; the fusion engine renormalizes weights across available empirical results. Three cultural engines use the Asia/Shanghai request time and calendar calculations, return reference-only records, and are rendered separately by Vue.

**Tech Stack:** Python 3.12, FastAPI, `lunar_python`, Spring Cloud Alibaba, PostgreSQL, Redis, RocketMQ, Vue 3, TypeScript, Vitest, Docker Compose.

---

### Task 1: Extend the dimension evidence contract

**Files:**
- Modify: `engines/base.py`
- Modify: `algorithm_service/models.py`
- Modify: `frontend/src/services/api.ts`
- Test: `tests/test_fusion.py`

1. Add category, availability status, scoring inclusion, weight, source URL/name, observation time, and sample size.
2. Make score and confidence nullable for unavailable/reference dimensions.
3. Add tests proving cultural and unavailable results cannot be scored.
4. Run `pytest tests/test_fusion.py -q`; expect all tests to pass.

### Task 2: Add cached real-evidence collectors

**Files:**
- Create: `data/evidence_feed.py`
- Modify: `data/data_feed.py`
- Test: `tests/test_evidence_feed.py`

1. Implement a thread-safe bounded TTL cache.
2. Fetch Open-Meteo production-region observations/forecast, Eastmoney product news, Eastmoney current trading limits/margin, and the existing real contract curve.
3. Preserve source URL and upstream observation time on every dataset.
4. Use short timeouts; return explicit unavailable evidence on failure.
5. Run collector tests with recorded JSON fixtures and failure cases.

### Task 3: Implement eleven empirical engines

**Files:**
- Create: `engines/empirical_engines.py`
- Modify: `engines/momentum_engine.py`
- Modify: `engines/indicators_engine.py`
- Modify: `engines/__init__.py`
- Test: `tests/test_engines.py`

1. Implement weather, news sentiment, supply-demand pressure, exchange-rule risk, positioning crowding, execution risk, cross-contract spread, term structure, and liquidity/volatility engines.
2. Retain the observed momentum and technical engines, adding evidence metadata.
3. Ensure every numeric output is derived from context evidence.
4. Return `UNAVAILABLE` with no score when mandatory evidence is absent.
5. Verify exactly eleven empirical engine keys.

### Task 4: Replace static cultural engines with real-time calendar calculations

**Files:**
- Create: `engines/cultural_reference_engines.py`
- Modify: `requirements.txt`
- Test: `tests/test_cultural_references.py`

1. Pin `lunar_python==1.4.8`.
2. Convert an injected timezone-aware Asia/Shanghai timestamp to lunar date, solar terms, and four pillars.
3. Derive Liu Yao, I Ching, and Qi Men reference displays deterministically from that time.
4. Return category `CULTURAL_REFERENCE`, status `REFERENCE`, weight zero, no score, and `includedInScore=false`.
5. Test fixed timestamps and prove output changes when the timestamp changes.

### Task 5: Fuse only available empirical evidence

**Files:**
- Modify: `config/settings.py`
- Modify: `engines/fusion_engine.py`
- Modify: `algorithm_service/app.py`
- Test: `tests/test_fusion.py`
- Test: `tests/test_algorithm_api.py`

1. Define weights for the eleven empirical keys only.
2. Gather upstream evidence concurrently before engine evaluation.
3. Normalize over available empirical weights; exclude unavailable and cultural records.
4. Return eleven empirical dimensions and three cultural references in separate response arrays.
5. Verify cultural changes cannot change composite score or action fields.

### Task 6: Render evidence and references distinctly

**Files:**
- Modify: `frontend/src/components/DimensionBars.vue`
- Modify: `frontend/src/views/StrategyView.vue`
- Modify: `frontend/src/views/OverviewView.vue`
- Modify: `frontend/src/styles/pages.css`
- Test: `frontend/src/components/DimensionBars.spec.ts`

1. Show source, observed time, sample size, status, weight, and key metrics on empirical cards.
2. Show unavailable dimensions without a score bar.
3. Add a separate cultural-reference section with a permanent non-empirical disclaimer.
4. Verify reference cards have no score, confidence, weight, or signal styling.

### Task 7: Verify, rebuild, and deploy

**Files:**
- Modify: `algorithm_service/Dockerfile` only if dependency installation requires it.
- Modify: `docs/verification.md`

1. Run Python, Java, and Vue test suites.
2. Build the Vue production bundle and Docker images.
3. Recreate algorithm, strategy, gateway, and frontend containers without deleting PostgreSQL or Redis volumes.
4. Verify `/api/v1/predictions/CJM` contains 11 empirical and 3 cultural records.
5. Verify all cultural weights are zero and excluded, all scored records have source metadata, and no production code contains demo/fake constants.
6. Verify the browser-facing endpoint at `http://127.0.0.1:8088/api/v1/predictions/CJM` returns HTTP 200.
