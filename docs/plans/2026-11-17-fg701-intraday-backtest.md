# FG701 intraday backtest implementation plan

**Goal:** Test the user's confirmed one-lot, one-minute intraday glass January 2027 strategy on complete trading days from 2026-10-17 through 2026-11-16.

**Architecture:** Isolated read-only TqSdk collection, immutable local raw evidence, and a deterministic bar-based simulator. No live orders or changes to running application services. Exact VWAP requires historical amount/average fields; OHLCV typical-price approximation requires user acceptance.

**Tech stack:** Python, TqSdk, standard-library CSV/JSON, pytest.

## Rules confirmed by user

- Actual delivery contract CZCE.FG701, never continuous FG0/FGM.
- One lot, one position maximum, symmetric long/short; no profit target.
- Initial entry: completed minute close above/below cumulative trading-day mean; execute next minute open.
- Fixed stop: 10 exchange ticks from actual entry, adverse gap fills at open plus slippage.
- Opposite close at least 3 ticks beyond current mean schedules exit at next minute open.
- After mean exit, wait for first pullback: touch within one tick on the breakout side, no intrabar crossing through mean, close on breakout side; enter next minute open. A failed pullback invalidates this breakout. A fresh opposite 3-tick breakout can arm the other direction.
- After a stop, reassess the following completed minute for a new initial entry. No same-bar reentry.
- Night session belongs to next provider calendar trading date; day-session 14:59 open is the planned liquidation time; no new positions at/after 14:58. Do not invent fills across missing session-end data.
- Convergence and trend filters deferred by user's explicit confirmation.

## Task 1: Collect and validate data

Create `scripts/collect_fg701_minutes.py`. Load credentials from environment or existing local infrastructure environment file without displaying them. Use TqSim for read-only quotes/serials, latest 10000 minute bars plus daily bars and provider trading calendar. Cache raw observations under ignored `data/history/fg701-intraday-2026-11-17/` with SHA-256 manifest. Confirm actual metadata, timestamp range, trading sessions, unique IDs and timestamps, missing minute counts and full-day coverage. If the latest serial cannot cover the window, try the provider's authorized historical download capability. Do not report unavailable data as successful backtest.

## Task 2: Simulator and checks

Create `scripts/backtest_fg701_intraday.py` with causal cumulative mean and next-open entries/exits, stop-first execution, no terminal provisional bars, and deterministic finite-state reversal. Tests in `tests/test_fg701_intraday.py` must cover long/short symmetry, exact 3-tick threshold, pullback failure, fixed stops/gaps, no same-bar reentry, daily reset/forced exit, and prefix invariance. Keep fees and adverse slippage explicit.

## Task 3: Run and report

Freeze the rule specification before examining profit. Run zero-cost diagnostic, one-tick-per-side baseline, and two-tick-per-side stress scenarios with a disclosed assumed fee if historical broker fees are unavailable. Export trades, daily P&L, curve, metadata and report under `output/fg701-intraday-2026-11-17/`. Report net/gross currency P&L, costs, win rate, profit factor, realized and marked drawdown, holding time and direction breakdown. No return-on-capital claim without a stated capital/margin model. The one-month result is descriptive, not out-of-sample proof.
