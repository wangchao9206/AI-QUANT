import pytest

from scripts.backtest_fg701_ma20_wait_cross import simulate_wait_cross,verify
from scripts.backtest_fg701_intraday import summarize
from tests.test_fg701_intraday import bar,end,mirror


def checked(rows,**kwargs):
    trades,curve,events=simulate_wait_cross(rows,**kwargs)
    verify(trades,curve,events,summarize(trades,curve))
    return trades,curve,events


def test_mean_exit_leaves_flat_and_does_not_reuse_exit_cross():
    rows=[bar(0,101),bar(1,101),bar(2,97),bar(3,96),bar(4,95),end(95)]
    trades,curve,events=checked(rows,slippage=0)
    assert len(trades)==1 and trades[0]['exitReason']=='MEAN_REVERSAL'
    assert len(events)==2 and curve[3]['position']==0
    assert all(c['position']==0 for c in curve[3:])


def test_new_upward_cross_after_mean_exit_reopens_long_next_open():
    rows=[bar(0,101),bar(1,101),bar(2,97),bar(3,96),bar(4,101),bar(5,102),end(105)]
    trades,_,_=checked(rows,slippage=0)
    assert [t['side'] for t in trades]==[1,1]
    assert trades[1]['entryReason']=='CROSS_AFTER_EXIT'
    assert trades[1]['signalTime']==rows[4]['timestamp'].isoformat()
    assert trades[1]['entryTime']==rows[5]['timestamp'].isoformat()
    assert trades[1]['crossFromDelta']==-4 and trades[1]['crossToDelta']==1
    assert trades[1]['previousExitTime']==trades[0]['exitTime']


def test_short_mean_exit_waits_for_new_downward_cross():
    rows=mirror([bar(0,101),bar(1,101),bar(2,97),bar(3,96),bar(4,101),bar(5,102),end(105)])
    trades,_,_=checked(rows,slippage=0)
    assert [t['side'] for t in trades]==[-1,-1]
    assert trades[1]['entryReason']=='CROSS_AFTER_EXIT'


def test_stop_does_not_reverse_and_exit_bar_cross_cannot_be_reused():
    rows=[bar(0,101),bar(1,99,opening=101,low=90,high=102),bar(2,98),end(98)]
    trades,curve,events=checked(rows,slippage=0)
    assert len(trades)==1 and trades[0]['exitReason']=='STOP'
    assert len(events)==2 and all(c['position']==0 for c in curve[1:])


def test_new_opposite_cross_after_stop_opens_only_on_next_minute():
    rows=[bar(0,101),bar(1,105,opening=101,low=90,high=105),bar(2,99),bar(3,98),end(98)]
    trades,_,_=checked(rows,slippage=0)
    assert [t['side'] for t in trades]==[1,-1]
    assert trades[1]['signalTime']==rows[2]['timestamp'].isoformat()
    assert trades[1]['entryTime']==rows[3]['timestamp'].isoformat()
    assert trades[1]['entryTime']>trades[0]['exitTime']


def test_opening_gap_stop_waits_and_cancels_pending_mean_exit():
    rows=[bar(0,101),bar(1,101),bar(2,97),bar(3,85),bar(4,84),end(84)]
    trades,_,events=checked(rows,slippage=0)
    assert len(trades)==1 and trades[0]['exitReason']=='STOP_GAP'
    assert trades[0]['exitPrice']==85 and len(events)==2


def test_mean_touch_alone_is_insufficient_for_reentry():
    rows=[bar(0,101),bar(1,105,opening=101,low=90,high=105),bar(2,100),bar(3,100),bar(4,99),bar(5,98),end(98)]
    trades,_,_=checked(rows,slippage=0)
    assert trades[1]['signalTime']==rows[4]['timestamp'].isoformat()
    assert trades[1]['entryTime']==rows[5]['timestamp'].isoformat()


def test_flat_cross_uses_zero_offset_not_held_exit_three_tick_threshold():
    rows=[bar(0,101),bar(1,105,opening=101,low=90,high=105),bar(2,99),bar(3,99),end(99)]
    trades,_,_=checked(rows,slippage=0)
    assert len(trades)==2 and trades[1]['crossToDelta']==-1


def test_reentry_that_stops_in_its_fill_minute_stays_flat_again():
    rows=[bar(0,101),bar(1,105,opening=101,low=90,high=105),bar(2,99),bar(3,98,high=110,low=98),bar(4,98),end(98)]
    trades,_,events=checked(rows,slippage=0)
    assert len(trades)==2 and trades[1]['exitReason']=='STOP'
    assert trades[1]['entryTime']==trades[1]['exitTime']
    assert all(not e['reason'].startswith('REVERSE_') for e in events)


@pytest.mark.parametrize('slip',[0,1,2])
def test_long_short_symmetry_and_explicit_path_equivalence(slip):
    rows=[bar(0,101),bar(1,105,opening=101,low=89,high=112),bar(2,99),bar(3,98),end(98)]
    a,_,_=checked(rows,slippage=slip,path='HIGH_FIRST')
    b,_,_=checked(mirror(rows),slippage=slip,path='LOW_FIRST')
    c,_,_=checked(rows,slippage=slip,path='LOW_FIRST')
    assert [t['netPnl'] for t in a]==[t['netPnl'] for t in b]==[t['netPnl'] for t in c]
    assert [t['side'] for t in a]==[-t['side'] for t in b]


def test_no_profit_target_and_normal_cost_accounting():
    trades,_,events=checked([bar(0,101),bar(1,120,opening=101),end(130)],slippage=1,fee=6)
    assert len(trades)==1 and trades[0]['exitReason']=='DAY_END'
    assert trades[0]['entryPrice']==102 and trades[0]['exitPrice']==129
    assert trades[0]['netPnl']==528
    assert trades[0]['fees']==12 and trades[0]['slippageCost']==40
    assert sum(e['fee'] for e in events)==12


def test_zero_volume_does_not_create_a_cross_signal_or_fill():
    rows=[bar(0,101),bar(1,105,opening=101,low=90,high=105),bar(2,99),bar(3,105),bar(4,99),bar(5,98),end(98)]
    rows[2]['volume']=0
    trades,_,_=checked(rows,slippage=0)
    assert trades[1]['signalTime']==rows[4]['timestamp'].isoformat()
    assert trades[1]['entryTime']==rows[5]['timestamp'].isoformat()


def test_post_close_wait_resets_for_initial_entry_on_next_day():
    first=[bar(0,101),bar(1,99,opening=101,low=90,high=102),end(98)]
    second=[bar(0,99,day='2026-11-03'),bar(1,98,day='2026-11-03'),end(98,day='2026-11-03')]
    trades,_,_=checked(first+second,slippage=0)
    assert len(trades)==2 and trades[1]['entryReason']=='INITIAL_SIDE'


def test_no_reentry_at_cutoff_and_daily_gap_liquidation_never_reenters():
    rows=[bar(0,101),bar(1,105,opening=101,low=90,high=105),bar(358,99),end(98)]
    assert len(checked(rows,slippage=0)[0])==1
    trades,curve,_=checked([bar(0,101),bar(1,101),end(60)],slippage=0)
    assert len(trades)==1 and trades[0]['exitReason']=='DAY_END' and curve[-1]['position']==0


def test_complete_day_prefix_does_not_use_future_prices():
    first=[bar(0,101),bar(1,101),bar(2,97),bar(3,96),bar(4,101),bar(5,102),end(105)]
    second=[bar(0,99,day='2026-11-03'),bar(1,98,day='2026-11-03'),end(98,day='2026-11-03')]
    a,ac,ae=checked(first,slippage=0)
    b,bc,be=checked(first+second,slippage=0)
    assert b[:len(a)]==a and bc[:len(ac)]==ac and be[:len(ae)]==ae


def test_missing_terminal_liquidation_fails():
    with pytest.raises(ValueError,match='terminal'):
        simulate_wait_cross([bar(0,101),bar(1,101)])
