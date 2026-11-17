from datetime import timedelta
import math

import pytest

from scripts.backtest_fg701_ma20 import add_ma20, simulate_reversal, verify_ma_signals
from tests.test_fg701_intraday import bar,end


def test_ma20_requires_twenty_closes_without_filling_early_values():
    rows=[bar(i,i+1) for i in range(21)]
    result=add_ma20(rows)
    assert all(b['mean'] is None for b in result[:19])
    assert result[19]['mean']==10.5 and result[20]['mean']==11.5


def test_warmup_is_real_previous_nineteen_closes_and_excess_is_discarded():
    result=add_ma20([bar(0,20),bar(1,21)],warmup=list(range(1,20)))
    assert [b['mean'] for b in result]==[10.5,11.5]
    assert add_ma20([bar(0,20)],warmup=[9999]+list(range(1,20)))[0]['mean']==10.5


def test_indicator_continues_across_trading_days_while_positions_reset():
    rows=[bar(0,20),bar(0,40,day='2026-11-03')]
    result=add_ma20(rows,warmup=list(range(1,20)))
    assert result[0]['mean']==10.5
    assert result[1]['mean']==12.45


def test_rest_intervals_do_not_create_candles_or_empty_periods():
    rows=[bar(0,20),bar(1,21)]
    rows[1]['timestamp']+=timedelta(hours=12)
    result=add_ma20(rows,warmup=list(range(1,20)))
    assert [b['mean'] for b in result]==[10.5,11.5]


def test_ma20_is_equal_weighted_and_replaces_old_vwap_values():
    rows=[bar(i,i+1,mean=9000) for i in range(20)]
    rows[0]['volume']=10000000
    result=add_ma20(rows)
    assert result[-1]['mean']==10.5


def test_future_prices_do_not_change_already_calculated_ma20():
    rows=[bar(i,100+i) for i in range(30)]
    warmup=list(range(81,100))
    short=add_ma20(rows[:15],warmup)
    full=add_ma20(rows,warmup)
    changed=add_ma20(rows[:15]+[bar(15,99999)],warmup)
    assert short==full[:15]==changed[:15]


def test_no_target_is_left_after_removing_profit_rule():
    rows=add_ma20([bar(0,100),bar(1,120,opening=100),end(130)],warmup=[80]*19)
    trades,curve,events=simulate_reversal(rows,slippage=0)
    assert len(trades)==1 and trades[0]['exitReason']=='DAY_END'
    assert trades[0]['exitPrice']==130
    assert trades[0]['netPnl']==588
    assert 'targetPrice' not in trades[0]
    assert verify_ma_signals(trades,curve,rows,events)['noTakeProfit']


def test_all_windows_match_independent_literal_reference():
    warmup=[81+i*.25 for i in range(19)]
    rows=[bar(i,100+(i%7)) for i in range(80)]
    result=add_ma20(rows,warmup)
    prices=warmup+[b['close'] for b in rows]
    assert all(b['mean']==math.fsum(prices[i:i+20])/20 for i,b in enumerate(result))


@pytest.mark.parametrize('bad',[float('nan'),0,-1])
def test_invalid_warmup_closes_are_rejected(bad):
    with pytest.raises(ValueError,match='warmup'):
        add_ma20([bar(0,100)],warmup=[bad]*19)
