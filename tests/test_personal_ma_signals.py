from types import SimpleNamespace

from backtesting.personal_ma_signals import ma_tape


def daily_bars(closes):
    return [SimpleNamespace(close=close) for close in closes]


def test_smas_warm_up_independently_and_only_strict_crossings_trigger():
    tape = ma_tape(daily_bars([100] * 20 + [110, 90, 89]))

    assert tape[3]['ma5'] is None
    assert tape[4]['ma5'] == 100
    assert tape[8]['ma10'] is None
    assert tape[9]['ma10'] == 100
    assert tape[18]['ma20'] is None
    assert tape[19] == dict(ma5=100, ma10=100, ma20=100, trend=0, trigger=None, strong=0)
    assert tape[20] == dict(ma5=102, ma10=101, ma20=100.5, trend=1, trigger='LONG_CROSS', strong=1)
    assert tape[21] == tape[19]
    assert tape[22] == dict(ma5=97.8, ma10=98.9, ma20=99.45, trend=-1, trigger='SHORT_CROSS', strong=-1)


def test_reentry_uses_previous_three_narrowing_gaps_through_a_bullish_cross():
    bars = daily_bars([100] * 30 + list(range(101, 121)) + [119, 118, 117, 116, 119, 122, 125])
    tape = ma_tape(bars)

    assert [(index, row['trigger']) for index, row in enumerate(tape) if row['trigger']] == [
        (30, 'LONG_CROSS'), (56, 'LONG_REENTRY'),
    ]
    assert tape[-1]['ma5'] - tape[-1]['ma20'] > tape[-2]['ma5'] - tape[-2]['ma20']
    assert tape[-1]['ma5'] > tape[-1]['ma10']
    assert tape[-2]['ma5'] <= tape[-2]['ma10']
    assert ma_tape(bars[:-1]) == tape[:-1]


def test_adapted_periods_and_convergence_change_the_trading_tape():
    bars = daily_bars([100] * 30 + list(range(101, 121)) + [119, 118, 117, 116, 119, 122, 125])

    slower_convergence = ma_tape(bars, convergence_days=20)
    assert [row['trigger'] for row in slower_convergence if row['trigger']] == ['LONG_CROSS']

    faster_averages = ma_tape(bars, periods=(2, 4, 8))
    assert [(index, row['trigger']) for index, row in enumerate(faster_averages) if row['trigger']] == [
        (30, 'LONG_CROSS'), (52, 'SHORT_CROSS'), (55, 'LONG_CROSS'),
    ]
