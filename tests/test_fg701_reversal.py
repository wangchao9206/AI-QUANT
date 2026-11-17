import pytest

from scripts.backtest_fg701_reversal import simulate_reversal, verify
from scripts.backtest_fg701_intraday import summarize
from tests.test_fg701_intraday import bar, end, mirror


def test_mean_exit_reverses_at_same_open_without_pullback():
    rows = [bar(0,99),bar(1,99),bar(2,103),bar(3,104),end(110)]
    trades, curve, events = simulate_reversal(rows,fee=0,slippage=0)
    assert [t['side'] for t in trades] == [-1,1]
    assert trades[0]['exitTime'] == trades[1]['entryTime'] == rows[3]['timestamp'].isoformat()
    assert trades[0]['exitPrice'] == trades[1]['entryPrice'] == 104
    assert trades[1]['entryReason'] == 'REVERSE_MEAN_REVERSAL'
    assert trades[0]['exitSequence']+1 == trades[1]['entrySequence']
    assert verify(trades,curve,events,summarize(trades,curve))['status'] == 'PASS'


def test_stop_reversal_resets_stop_from_actual_fill_and_charges_both_legs():
    rows = [bar(0,101),bar(1,95,opening=101,low=90,high=102),end(90)]
    trades, curve, events = simulate_reversal(rows,fee=6,slippage=1)
    assert trades[0]['stopPrice'] == 92
    assert trades[0]['exitPrice'] == 91
    assert trades[1]['entryPrice'] == 91
    assert trades[1]['side'] == -1 and trades[1]['stopPrice'] == 101
    assert trades[1]['entryReason'] == 'REVERSE_STOP'
    assert trades[0]['exitTime'] == trades[1]['entryTime']
    assert trades[0]['exitPhase'] == trades[1]['entryPhase'] == 'SEGMENT_2'
    assert len(events) == 4 and sum(e['fee'] for e in events) == 24
    assert all(t['fees'] == 12 and t['slippageCost'] == 40 for t in trades)
    verify(trades,curve,events,summarize(trades,curve))


def test_gap_stop_reverses_at_actual_gap_open():
    rows = [bar(0,101),bar(1,101),bar(2,85),end(85)]
    trades, _, _ = simulate_reversal(rows,fee=0,slippage=0)
    assert trades[0]['exitReason'] == 'STOP_GAP'
    assert trades[0]['exitPrice'] == trades[1]['entryPrice'] == 85
    assert trades[1]['entryReason'] == 'REVERSE_STOP_GAP'


def test_path_scenarios_preserve_different_intrabar_stop_orders():
    rows = [bar(0,101),bar(1,89,opening=101,high=112,low=89),end(89)]
    hi,_,_ = simulate_reversal(rows,fee=0,slippage=0,path='HIGH_FIRST')
    lo,_,_ = simulate_reversal(rows,fee=0,slippage=0,path='LOW_FIRST')
    assert hi[0]['exitPhase'] == 'SEGMENT_2'
    assert lo[0]['exitPhase'] == 'SEGMENT_1'
    assert len(hi) == 2 and len(lo) == 4
    assert [t['side'] for t in lo] == [1,-1,1,-1]


@pytest.mark.parametrize('slip',[0,1,2])
def test_mirror_long_short_and_mirror_path_symmetry(slip):
    rows = [bar(0,101),bar(1,100,opening=101,high=112,low=89),end(100)]
    a,ac,ae = simulate_reversal(rows,slippage=slip,path='HIGH_FIRST')
    b,bc,be = simulate_reversal(mirror(rows),slippage=slip,path='LOW_FIRST')
    assert [t['netPnl'] for t in a] == [t['netPnl'] for t in b]
    assert [t['side'] for t in a] == [-t['side'] for t in b]
    verify(a,ac,ae,summarize(a,ac))
    verify(b,bc,be,summarize(b,bc))


def test_day_end_gap_liquidates_once_without_reversal():
    trades,curve,events = simulate_reversal([bar(0,101),bar(1,101),end(70)],slippage=0)
    assert len(trades) == 1 and trades[0]['exitReason'] == 'DAY_END'
    assert len(events) == 2 and curve[-1]['position'] == 0


def test_stop_at_entry_cutoff_closes_without_creating_late_position():
    rows = [bar(0,101),bar(1,101),bar(358,85),end(85)]
    trades,curve,events = simulate_reversal(rows,slippage=0)
    assert len(trades) == 1 and trades[0]['exitReason'] == 'STOP_GAP'
    assert curve[-1]['position'] == 0
    verify(trades,curve,events,summarize(trades,curve))


def test_empty_volume_does_not_execute_pending_reversal():
    rows = [bar(0,99),bar(1,99),bar(2,103),bar(3,104),bar(4,105),end(110)]
    rows[3]['volume'] = 0
    trades,_,_ = simulate_reversal(rows,slippage=0)
    assert trades[0]['exitTime'] == trades[1]['entryTime'] == rows[4]['timestamp'].isoformat()


def test_complete_day_prefix_is_unchanged_by_future_days():
    first = [bar(0,99),bar(1,99),bar(2,103),bar(3,104),end(110)]
    second = [bar(0,101,day='2026-11-03'),bar(1,100,opening=101,high=112,low=89,day='2026-11-03'),end(100,day='2026-11-03')]
    a,ac,ae = simulate_reversal(first)
    b,bc,be = simulate_reversal(first+second)
    assert b[:len(a)] == a and bc[:len(ac)] == ac and be[:len(ae)] == ae


def test_missing_terminal_liquidation_is_an_error():
    with pytest.raises(ValueError,match='terminal'):
        simulate_reversal([bar(0,101),bar(1,101)])
