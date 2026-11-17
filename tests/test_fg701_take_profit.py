import pytest

from scripts.backtest_fg701_take_profit import simulate_take_profit, verify
from scripts.backtest_fg701_intraday import summarize
from tests.test_fg701_intraday import bar, end, mirror


def checked(rows, **kwargs):
    trades, curve, events = simulate_take_profit(rows, **kwargs)
    verify(trades, curve, events, summarize(trades, curve))
    return trades, curve, events


@pytest.mark.parametrize('slip',[0,1,2])
def test_target_is_ten_ticks_from_actual_fill_and_exit_costs_are_separate(slip):
    rows=[bar(0,101),bar(1,112,opening=101,low=101,high=114),bar(2,114),end(114)]
    trades,curve,events=checked(rows,slippage=slip,fee=6)
    assert len(trades)==1 and len(events)==2
    t=trades[0]
    assert t['targetPrice']==101+slip+10
    assert t['exitReason']=='TAKE_PROFIT' and t['exitReference']==t['targetPrice']
    assert t['netPnl']==(10-slip)*20-12
    assert curve[1]['position']==0 and curve[1]['waitingForCross']


def test_no_reentry_just_because_price_stays_above_mean_after_profit():
    rows=[bar(0,101),bar(1,111,opening=101),bar(2,112),bar(3,113),end(114)]
    trades,_,events=checked(rows,slippage=0)
    assert len(trades)==1 and all(e['reason']!='CROSS_AFTER_TP' for e in events)


def test_new_downward_cross_enters_short_next_open_with_less_than_three_tick_offset():
    rows=[bar(0,101),bar(1,111,opening=101),bar(2,99),bar(3,98),end(98)]
    trades,_,_=checked(rows,slippage=0)
    assert len(trades)==2 and trades[1]['side']==-1
    assert trades[1]['entryReason']=='CROSS_AFTER_TP'
    assert trades[1]['signalTime']==rows[2]['timestamp'].isoformat()
    assert trades[1]['entryTime']==rows[3]['timestamp'].isoformat()
    assert trades[1]['crossFromDelta']==11 and trades[1]['crossToDelta']==-1


def test_new_upward_cross_after_short_profit_is_symmetric():
    rows=mirror([bar(0,101),bar(1,111,opening=101),bar(2,99),bar(3,98),end(98)])
    trades,_,_=checked(rows,slippage=0)
    assert trades[0]['side']==-1 and trades[0]['exitReason']=='TAKE_PROFIT'
    assert trades[1]['side']==1 and trades[1]['entryReason']=='CROSS_AFTER_TP'


def test_crossing_inside_profit_minute_is_not_reused():
    rows=[bar(0,101),bar(1,99,opening=101,high=111,low=99),bar(2,98),bar(3,97),end(97)]
    trades,_,_=checked(rows,slippage=0,path='HIGH_FIRST')
    assert len(trades)==1 and trades[0]['exitReason']=='TAKE_PROFIT'


def test_touch_at_mean_does_not_enter_until_a_later_close_breaks_it():
    rows=[bar(0,101),bar(1,111,opening=101),bar(2,100),bar(3,100),bar(4,101),bar(5,102),end(102)]
    trades,_,_=checked(rows,slippage=0)
    assert trades[1]['signalTime']==rows[4]['timestamp'].isoformat()
    assert trades[1]['entryTime']==rows[5]['timestamp'].isoformat()
    assert trades[1]['side']==1


def test_target_and_stop_in_one_minute_follow_both_explicit_paths():
    rows=[bar(0,101),bar(1,100,opening=101,high=112,low=89),end(100)]
    high,_,_=checked(rows,slippage=0,path='HIGH_FIRST')
    low,_,_=checked(rows,slippage=0,path='LOW_FIRST')
    assert high[0]['exitReason']=='TAKE_PROFIT'
    assert low[0]['exitReason']=='STOP'
    assert low[1]['entryReason']=='REVERSE_STOP'
    assert high[0]['entryPrice']+10==high[0]['targetPrice']
    assert low[1]['targetPrice']==low[1]['entryPrice']-10


def test_stop_then_reverse_then_profit_can_all_happen_on_same_monotonic_segment():
    rows=[bar(0,101),bar(1,75,opening=101,high=101,low=75),end(75)]
    trades,_,events=checked(rows,slippage=0)
    assert [t['exitReason'] for t in trades]==['STOP','TAKE_PROFIT']
    assert trades[0]['exitTime']==trades[1]['entryTime']==trades[1]['exitTime']
    assert trades[1]['entryPhase']==trades[1]['exitPhase']=='SEGMENT_2'
    assert len(events)==4


def test_mean_exit_still_reverses_and_resets_target():
    rows=[bar(0,99),bar(1,99),bar(2,103),bar(3,104),end(104)]
    trades,_,_=checked(rows,slippage=1)
    assert len(trades)==2
    assert trades[0]['exitReason']=='MEAN_REVERSAL'
    assert trades[0]['exitTime']==trades[1]['entryTime']
    assert trades[1]['entryReason']=='REVERSE_MEAN_REVERSAL'
    assert trades[1]['targetPrice']==trades[1]['entryPrice']+10


def test_favorable_target_gap_uses_target_and_does_not_reverse():
    rows=[bar(0,101),bar(1,101),bar(2,130),end(130)]
    trades,_,events=checked(rows,slippage=0)
    assert len(trades)==1 and trades[0]['exitReason']=='TAKE_PROFIT'
    assert trades[0]['exitReference']==111
    assert trades[0]['exitPhase']=='OPEN_TARGET_GAP' and len(events)==2


def test_gap_target_cancels_preexisting_pending_mean_reversal():
    rows=[bar(0,101),bar(1,101),bar(2,97),bar(3,120),end(120)]
    trades,_,_=checked(rows,slippage=0)
    assert len(trades)==1 and trades[0]['exitReason']=='TAKE_PROFIT'


def test_adverse_gap_stop_still_reverses():
    rows=[bar(0,101),bar(1,101),bar(2,85),end(85)]
    trades,_,_=checked(rows,slippage=0)
    assert trades[0]['exitReason']=='STOP_GAP'
    assert trades[1]['entryReason']=='REVERSE_STOP_GAP'
    assert trades[1]['entryTime']==trades[0]['exitTime']


def test_wait_state_resets_on_next_trading_day():
    first=[bar(0,101),bar(1,111,opening=101),end(112)]
    second=[bar(0,101,day='2026-11-03'),bar(1,101,day='2026-11-03'),end(101,day='2026-11-03')]
    trades,_,_=checked(first+second,slippage=0)
    assert trades[1]['entryReason']=='INITIAL_SIDE'
    assert trades[1]['tradingDay']=='2026-11-03'


def test_cross_after_cutoff_does_not_create_late_entry():
    rows=[bar(0,101),bar(1,111,opening=101),bar(358,99),end(98)]
    trades,_,_=checked(rows,slippage=0)
    assert len(trades)==1


def test_day_end_liquidation_has_priority_over_target_gap():
    trades,_,_=checked([bar(0,101),bar(1,101),end(130)],slippage=0)
    assert len(trades)==1 and trades[0]['exitReason']=='DAY_END'


@pytest.mark.parametrize('slip',[0,1,2])
def test_target_strategy_is_long_short_symmetric_for_mirrored_paths(slip):
    rows=[bar(0,101),bar(1,100,opening=101,high=112,low=89),bar(2,101),bar(3,99),bar(4,98),end(98)]
    a,_,_=checked(rows,slippage=slip,path='HIGH_FIRST')
    b,_,_=checked(mirror(rows),slippage=slip,path='LOW_FIRST')
    assert [t['netPnl'] for t in a]==[t['netPnl'] for t in b]
    assert [t['side'] for t in a]==[-t['side'] for t in b]


def test_future_days_do_not_change_past_profit_exit_or_cross_entry():
    first=[bar(0,101),bar(1,111,opening=101),bar(2,99),bar(3,98),end(98)]
    second=[bar(0,101,day='2026-11-03'),bar(1,101,day='2026-11-03'),end(101,day='2026-11-03')]
    a,ac,ae=checked(first,slippage=0)
    b,bc,be=checked(first+second,slippage=0)
    assert b[:len(a)]==a and bc[:len(ac)]==ac and be[:len(ae)]==ae


def test_zero_volume_does_not_trigger_profit_or_cross():
    rows=[bar(0,101),bar(1,101),bar(2,120),bar(3,111,opening=101),bar(4,99),bar(5,98),end(98)]
    rows[2]['volume']=0
    trades,_,_=checked(rows,slippage=0)
    assert trades[0]['exitTime']==rows[3]['timestamp'].isoformat()
    assert trades[1]['entryTime']==rows[5]['timestamp'].isoformat()
