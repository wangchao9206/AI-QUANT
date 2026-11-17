from datetime import datetime, timedelta

import pytest

from scripts.backtest_fg701_intraday import SH, add_mean, prepare, simulate, summarize


def bar(minute, close, opening=None, low=None, high=None, day='2026-11-02', mean=100):
    stamp = datetime.fromisoformat(day+'T09:00:00').replace(tzinfo=SH)+timedelta(minutes=minute)
    opening = close if opening is None else opening
    return dict(timestamp=stamp, tradingDay=day, open=opening, close=close,
                low=min(opening, close) if low is None else low,
                high=max(opening, close) if high is None else high, volume=100, mean=mean)


def end(close=105, day='2026-11-02'):
    return bar(359, close, day=day)


def mirror(rows):
    return [{**b, 'open': 200-b['open'], 'close': 200-b['close'],
             'low': 200-b['high'], 'high': 200-b['low'], 'mean': 200-b['mean']} for b in rows]


def test_initial_signal_fills_next_open_and_scheduled_day_end():
    rows = [bar(0, 101), bar(1, 103), end(110)]
    trades, curve = simulate(rows, fee=0, slippage=0)
    assert len(trades) == 1
    assert trades[0]['entryTime'] == rows[1]['timestamp'].isoformat()
    assert trades[0]['signalTime'] == rows[0]['timestamp'].isoformat()
    assert trades[0]['entryPrice'] == 103
    assert trades[0]['exitReason'] == 'DAY_END'
    assert trades[0]['netPnl'] == 140
    assert curve[-1]['position'] == 0


def test_opposite_three_ticks_is_inclusive_and_two_ticks_holds():
    rows = [bar(0, 99), bar(1, 99), bar(2, 102), bar(3, 103), bar(4, 104), end(104)]
    trades, _ = simulate(rows, fee=0, slippage=0)
    assert trades[0]['exitReason'] == 'MEAN_REVERSAL'
    assert trades[0]['exitTime'] == rows[4]['timestamp'].isoformat()


def reversal_rows():
    return [bar(0, 99), bar(1, 99), bar(2, 103),
            bar(3, 103, opening=104, low=100.5, high=104), bar(4, 104), end(110)]


def test_first_valid_pullback_opens_opposite_on_following_bar():
    rows = reversal_rows()
    trades, _ = simulate(rows, fee=0, slippage=0)
    assert [t['side'] for t in trades] == [-1, 1]
    assert trades[1]['entryReason'] == 'FIRST_PULLBACK'
    assert trades[1]['entryTime'] == rows[4]['timestamp'].isoformat()
    assert trades[1]['entryTime'] > trades[0]['exitTime']


def test_crossing_mean_invalidates_pullback_and_later_retouch_does_not_rearm():
    rows = reversal_rows()
    rows[3]['low'] = 99
    rows.insert(4, bar(4, 103, low=100.5))
    rows[5] = bar(5, 104)
    trades, _ = simulate(rows, fee=0, slippage=0)
    assert len(trades) == 1


def test_distant_pullback_does_not_count_as_touch():
    rows = reversal_rows()
    rows[3]['low'] = 102
    trades, _ = simulate(rows, fee=0, slippage=0)
    assert len(trades) == 1


@pytest.mark.parametrize('slip', [0, 1, 2])
def test_long_short_mirror_symmetry(slip):
    a, _ = simulate(reversal_rows(), fee=6, slippage=slip)
    b, _ = simulate(mirror(reversal_rows()), fee=6, slippage=slip)
    assert len(a) == len(b)
    assert [t['netPnl'] for t in a] == [t['netPnl'] for t in b]
    assert [t['side'] for t in a] == [-t['side'] for t in b]


def test_stop_uses_actual_entry_and_costs_reconcile():
    rows = [bar(0, 101), bar(1, 101, low=90, high=102), end()]
    trades, curve = simulate(rows, fee=6, slippage=1)
    t = trades[0]
    assert t['entryPrice'] == 102
    assert t['stopPrice'] == 92
    assert t['exitPrice'] == 91
    assert t['netPnl'] == -232
    assert t['grossPnl']-t['slippageCost']-t['fees'] == t['netPnl']
    assert t['exitReason'] == 'STOP'
    assert curve[1]['position'] == 0


def test_gap_stop_fills_adverse_open_before_mean_signal_exit():
    rows = [bar(0, 101), bar(1, 101), bar(2, 97), bar(3, 85), end(85)]
    trades, _ = simulate(rows, fee=0, slippage=0)
    assert trades[0]['exitReason'] == 'STOP_GAP'
    assert trades[0]['exitPrice'] == 85


def test_stop_cannot_reenter_same_bar():
    rows = [bar(0, 101), bar(1, 101, low=90), bar(2, 102), bar(3, 103), end()]
    trades, _ = simulate(rows, fee=0, slippage=0)
    assert len(trades) == 2
    assert trades[1]['signalTime'] == rows[2]['timestamp'].isoformat()
    assert trades[1]['entryTime'] == rows[3]['timestamp'].isoformat()


def test_no_entry_at_last_minute_and_missing_liquidation_fails():
    rows = [bar(358, 101), end()]
    assert simulate(rows)[0] == []
    with pytest.raises(ValueError, match='terminal position'):
        simulate([bar(0, 101), bar(1, 101)])
    with pytest.raises(ValueError, match='overnight'):
        simulate([bar(0, 101), bar(1, 101), bar(0, 101, day='2026-11-03')])


def test_cumulative_mean_resets_and_is_prefix_invariant():
    rows = [bar(0, 100), bar(1, 106), bar(0, 120, day='2026-11-03')]
    full = add_mean(rows)
    assert full[1]['mean'] == 103
    assert full[2]['mean'] == 120
    assert add_mean(rows[:2]) == full[:2]
    changed = rows + [bar(1, 10000, day='2026-11-03')]
    assert add_mean(changed)[:3] == full


def test_full_day_prefix_results_do_not_use_future_days():
    first = [bar(0, 101), bar(1, 102), end(110)]
    second = [bar(0, 99, day='2026-11-03'), bar(1, 98, day='2026-11-03'), end(80, day='2026-11-03')]
    t1, c1 = simulate(first, slippage=0)
    t2, c2 = simulate(first+second, slippage=0)
    assert t2[:len(t1)] == t1
    assert c2[:len(c1)] == c1
    s = summarize(t2, c2)
    assert s['grossPnl']-s['fees']-s['slippageCost'] == s['netPnl']


def test_volume_zero_does_not_fill_an_order():
    rows = [bar(0, 101), bar(1, 102), bar(2, 103), end()]
    rows[1]['volume'] = 0
    trades, _ = simulate(rows, slippage=0)
    assert trades[0]['entryTime'] == rows[2]['timestamp'].isoformat()


def test_data_audit_rejects_missing_session_instead_of_shortening_window():
    stamp = int(datetime(2026, 11, 2, 9, tzinfo=SH).timestamp()*1e9)
    raw = {'symbol': 'CZCE.FG701', 'calendar': [{'date': '2026-11-02', 'trading': True}],
           'minute': [{'id': 1, 'datetime': stamp, 'open': 100, 'high': 100, 'low': 100, 'close': 100, 'volume': 10}]}
    _, audit = prepare(raw)
    assert audit['status'] == 'FAIL'
    assert audit['coverage'][0]['bars'] == 1
    assert len(audit['coverage'][0]['missingMinutes']) == 344
