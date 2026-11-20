from datetime import date, datetime, time

from backtesting.personal_ma_multiframe_execution import run_multiframe_account
from data.data_feed import KLineBar
from data.trading_day import SHANGHAI
from data.tqsdk_backtest import FuturesContractSpec


def clock(day, hour, minute=0):
    return datetime.combine(day, time(hour, minute), SHANGHAI)


def sample():
    a, b, c = (date(2026, 11, day) for day in (2, 3, 4))
    bars = [KLineBar(clock(day, hour, minute), 100, 101, 99, 100, 100, 0, 'TEST')
            for day in (b, c) for hour, minute in ((9, 0), (9, 15), (9, 30), (14, 45))]
    daily = {a: {'trend': 1, 'trigger': 'LONG_CROSS'}, b: {'trend': -1, 'trigger': 'SHORT_CROSS'},
             c: {'trend': -1, 'trigger': None}}
    return a, b, c, bars, daily, FuturesContractSpec('TEST', 1, 1, 10, 1)


def test_primary_waits_for_fresh_confirmation_then_next_open_and_exit_ignores_gate():
    a, b, c, bars, daily, spec = sample()
    result = run_multiframe_account(bars, [b] * 4 + [c] * 4, daily, spec, b, c,
                                    confirmations={clock(a, 14, 45): 1, clock(b, 9, 15): 1})
    assert result['metrics']['primaryOpens'] == 1
    [trade] = result['trades']
    assert trade['entryAt'] == clock(b, 9, 15).isoformat()
    assert trade['exitAt'] == clock(c, 9).isoformat()
    assert trade['exitReason'] == 'MA_REVERSAL'


def test_second_minute_signal_adds_once_only_when_allowed_and_keeps_short_half_size():
    _, b, c, bars, daily, spec = sample()
    gates = {clock(b, 9): (1,), clock(b, 9, 15): (1,), clock(b, 9, 30): (1,),
             clock(c, 9): (-1,), clock(c, 9, 15): (-1,)}
    args = (bars, [b] * 4 + [c] * 4, daily, spec, b, c)
    strict = run_multiframe_account(*args, confirmations=gates)
    result = run_multiframe_account(*args, confirmations=gates, minute_add=True)
    assert strict['metrics']['addOpens'] == 0
    assert result['metrics']['primaryOpens'] == 2
    assert result['metrics']['addOpens'] == 1
    assert [item['entryAt'] for item in result['decisions']] == [clock(b, 9).isoformat(),
                                                              clock(b, 9, 15).isoformat(), clock(c, 9).isoformat()]
    assert [leg['exitAt'] for leg in result['trades'][:2]] == [clock(c, 9).isoformat()] * 2
    assert result['metrics']['netPnl'] == -12
