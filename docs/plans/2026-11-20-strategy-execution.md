# Strategy Execution Implementation Plan

**Goal:** Make explicitly defined strategies available for historical replay and simulated execution, preserving each strategy's own rules and reporting unsupported cases honestly.

**Architecture:** Use versioned strategy configurations and a shared causal decision contract. Historical replay and paper execution consume the same decisions; paper execution persists decisions, order state and recovery checkpoints transactionally. Live brokerage is out of scope.

**Tech stack:** Python/FastAPI, Java/Spring, PostgreSQL/Flyway, Vue, existing paper matching engine.

## Current findings

- `algorithm_service/personal_trinity.py` only replays a verified fixed archive; it is not a paper execution adapter. Its browser drafts are stored locally.
- `PaperAutomationService` supports MA20_MACD, HOLISTIC_14D, MOMENTUM_BREAKOUT, BOLLINGER_REVERSAL, DUAL_THRUST, ADAPTIVE_CTA, BUY_AND_HOLD and WORKFLOW. Its current flat-entry restriction explicitly prevents adding and immediate reversal.
- The automation minute feed is limited to 180 one-minute bars. Completed 15/30/60-minute Chan/Wyckoff structure requires sufficient contiguous, session-aligned history and explicit exchange trading dates. Do not infer missing data.
- The three-in-one replay opens one lot per half and supports long-side additions. Its rule semantics must remain consistent when adapting it to paper execution; a single contract cannot be divided into half a lot.
- No real brokerage connection is authorized for this work. Existing running simulations must not be modified or started implicitly.

## Work

1. Inventory executable strategies and their parameter, history and mode requirements. Display actual capability and explicit failure reasons in the strategy center.
2. Extract a deterministic, versioned decision state machine from the three-in-one replay. Cover completed bars, exchange sessions, MA reversals, pending confirmation expiry, Chan OR Wyckoff, long additions, partial fills and restart replay. Compare emitted decisions against existing historical execution with fixed data and prefix tests.
3. Store immutable strategy version, contract, execution sizing and state with tenant isolation. Persist decisions and order/fill checkpoints atomically; make retries and restart reconciliation idempotent.
4. Extend the paper feed to obtain enough validated daily and minute history, completed bars, actual contract, trading sessions and trading dates. Refuse execution on gaps, stale quotes or uncertain session mapping.
5. Extend paper automation for partial entry, add-on and close-before-reverse. Preserve existing strategy behavior. Respect exchange integer lot sizes, exposure and risk checks. Never infer a fill from an order submission.
6. Connect the strategy editor and strategy center to historical runs and explicitly user-started paper sessions. Keep existing browser drafts intact and snapshot the selected configuration into each run.
7. Verify existing strategies, no-lookahead consistency, repeat and restart idempotency, rejected/partial orders, data gaps, tenant isolation and upgrade migration. Run integration tests against a disposable database before deployment.
