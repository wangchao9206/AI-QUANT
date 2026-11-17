# FG701 10-tick take-profit and mean-cross reentry

User revision: add a fixed 10-tick profit target; following a take-profit close, remain flat until a new crossing of the current trading-day mean. Retain all other previously tested rules and the same data and execution costs.

## Frozen rules before examining results

- One lot, one position, actual CZCE.FG701, 21 complete trading days, causal cumulative HLC3 volume-weighted approximate VWAP. Day/session definitions and original source stay unchanged.
- Every entry, including a reversal, resets its stop and target to 10 exchange ticks below/above actual filled entry, symmetrically for shorts. Target reference is entry +/-10 ticks. Exits still incur adverse market slippage: a 10-tick target is not a guaranteed net 10-tick gain. Favorable opening gaps do not improve the target reference fill beyond the target.
- Initial entry is above/below mean, next observed minute open. The existing mean-exit threshold remains 3 ticks, close-confirmed and executed next open with immediate opposite entry. Stops still immediately reverse. Both close and opposite open pay separate fees/slippage.
- Take-profit closes do not reverse. Ignore preexisting pending mean-exit signals once the profit target fills. The take-profit minute's completed close establishes the first crossing baseline; do not reuse a crossing from earlier in that minute.
- After take profit, a later completed close with previous close-minus-mean <=0 and current close-minus-mean >0 schedules a long; previous >=0 and current <0 schedules a short. Touching the line alone is insufficient. Compare each close to its own contemporaneous mean. Execute at next observed open. This new crossing does not need a 3-tick offset; 3 ticks remains the held-position exit condition.
- No reentry on the take-profit minute, and no same-side reentry from merely remaining above/below mean. Once reentered, normal stop/mean-exit reversal rules resume. Reset the wait state at the next trading day.
- 14:58 entry cutoff and 14:59 open planned liquidation are retained. No reversal or entry at/after cutoff. Daily liquidation has priority and never creates another position.
- Run independent fixed O-H-L-C and O-L-H-C routes for unknown intraminute ordering. Within each monotonic segment, allow a stop/reversal followed by the opposite position's profit target; stop processing once take profit leaves the strategy flat. Report both paths; do not infer exact tick timing or guaranteed bounds.
- Opening protective orders precede pending mean signals: adverse stop gaps reverse, favorable target gaps take profit and wait. Minute-level fill timestamps plus event phase/sequence only.

## Implementation and verification

Create an independent simulator `scripts/backtest_fg701_take_profit.py`, tests `tests/test_fg701_take_profit.py`, and immutable results under `output/fg701-take-profit-2026-11-17/`. Retain prior studies. Test symmetric targets, reset after reversal, no immediate take-profit reversal, no stale or same-bar crossing reuse, true post-profit crossings in both directions, unchanged stop/mean reversals, gap order priority, both path scenarios, costs and no trading-day carry. Reconcile all fill/trade/day/curve accounting and independently validate the crossing recorded by every post-profit entry.

Update a new interactive chart with take-profit labels and the selected 2026-10-28 date. Include separate path views only if their plotted fills differ; disclose scenario identity in labels. Check all dates/views and narrow-width marker geometry.
