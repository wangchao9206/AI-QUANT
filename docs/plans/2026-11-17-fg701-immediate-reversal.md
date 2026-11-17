# FG701 close-and-reverse revision

User revision: reverse direction whenever a position closes. Preserve one lot, 10-tick fixed stop, no profit target, cumulative approximate VWAP, 3-tick reverse mean exit, original complete 21 trading days, and costs. Day-end liquidation and the existing 14:58 entry cutoff prohibit a new position.

## Frozen execution rules

- Initial entries and mean exits continue to use completed-minute signals and the next observed open.
- A mean exit closes the existing lot and opens one opposite lot at that same open. Do not wait for a pullback, and do not require a second entry signal.
- Stops also close and immediately open the opposite lot at the stop reference, or at the adverse opening price on a gap. Each close and open separately incurs adverse slippage and fees. Reset the fixed stop from the new actual entry price.
- A reversal need not meet the original first-entry VWAP-side condition; it follows the user's instruction to reverse on each close.
- OHLC cannot reveal intraminute stop/reversal ordering. Run two fixed paths independently: O-H-L-C and O-L-H-C. These are explicit modeling scenarios, not guaranteed bounds on actual execution. Never choose a path retrospectively from its profit. Intrabar events share the bar timestamp and use sequence numbers, without fabricated second-level timestamps.
- Follow a monotonic price segment through a stop, reverse, then continue that segment and subsequent segments. A newly reversed position may stop again later in that minute. At most one stop per monotonic segment for slippage less than the stop distance.
- Day-end liquidation at 14:59 open does not reverse, including opening gaps at that scheduled liquidation time. At/after 14:58 no new reversal entry is allowed; existing positions remain subject to stops and forced liquidation.
- Keep baseline scripts and frozen results untouched. New script imports the existing preparation and summary helpers and records all source hashes.

## Implementation and verification

1. Add `scripts/backtest_fg701_reversal.py`, a segment-based event simulator, new immutable results, all fill events, and both path ledgers under `output/fg701-reversal-2026-11-17/`.
2. Add tests for immediate mean/gap/stop reversals, reset stops, multiple events within a minute, both path differences, long/short symmetry with mirrored paths, fee reconciliation, no overlapping exposure, end-of-day exceptions, and prefix invariance.
3. Verify every close before cutoff is followed by one opposite entry at the same reference price, with independent costs, and every day ends flat. Compare old and new results on unchanged data and cost assumptions.
4. Create a new interactive buy/sell chart with both intrabar assumptions, preserve the currently selected 2026-10-27 date, and group coincident close/open markers so both remain inspectable. Verify all dates, views, paths, and narrow-width geometry before returning the chart.
