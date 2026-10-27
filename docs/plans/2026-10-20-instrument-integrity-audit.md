# Instrument identity and workflow integrity audit

**Goal:** Fix cross-product contract navigation and other reproducible errors that mix instruments, accounts, or executed results.

**Architecture:** Treat product roots and full instrument identifiers as different inputs. Keep requested identity attached to asynchronous responses; only show or act on results for the current selection. Preserve the existing Vue / Java / Python service boundaries.

**Tech Stack:** Vue 3, Pinia, TypeScript, Vitest, FastAPI, pytest, Spring Boot.

## 1. Reproduce instrument identity failures

- Add frontend regression cases for JM, M, PM, SM and IM delivery contracts and their continuous symbols.
- Add primary and fallback feed tests for bare product roots, with overlapping roots (J/JM, M/PM/SM/IM).
- Exercise the actual ladder click and subsequent requests, rather than mocking away the store.

## 2. Repair identity handling

- Centralize frontend extraction in `frontend/src/utils/marketNavigation.ts`.
- Make `term_snapshot` accept an explicit product root; adapt callers that currently pass a full symbol.
- Prevent foreign-product curves and stale instrument data from being displayed as the selected product.
- Verify against the full local product catalog and Zhengzhou contract aliases.

## 3. Audit adjacent user workflows

- Inspect route/store synchronization and asynchronous market loads.
- Inspect paper-account selection, requests in flight, order forms and confirmations.
- Inspect backtest form edits versus frozen execution results.
- Reproduce each additional finding before applying a focused fix and regression test.

## 4. Verify and deliver

- Run targeted regressions first, then frontend tests and production build, Python tests, and relevant Java checks if changed.
- Check live local responses where available without altering user accounts or orders.
- Record confirmed defects, test results and remaining verification limits. Do not claim exhaustive correctness or deploy unrequested changes.

## Outcome

- Completed the code audit and focused fixes; confirmed issues and verification evidence are recorded in `docs/verification.md` under 2026-10-20.
- Python: 352 passing; frontend: 180 passing; native and Linux production builds pass.
- Applied the repair to the existing local frontend and algorithm containers. Read-only checks against all 87 product curves found no foreign-product contracts; five products correctly had empty curves.
- Preserved account records and existing frozen research/backtest artifacts; no live browser order or account mutation was used for verification.
