"""Execution ordering for MA reversals, add-ons and contract changes."""

from datetime import datetime, timedelta, timezone

import pytest

from backtesting.personal_ma_execution import run_account
from data.data_feed import KLineBar
from data.tqsdk_backtest import FuturesContractSpec, RollEvent, TqSdkBacktestDataset


def make_dataset(prices, roll_index=None):
    begin = datetime(2020, 1, 1, tzinfo=timezone.utc)
    bars = [KLineBar(begin + timedelta(days=i), price, price + 2, price - 2, price, 10_000, 50_000,
                     'NEW' if roll_index is not None and i >= roll_index else 'OLD')
            for i, price in enumerate(prices)]
    rolls = []
    if roll_index is not None:
        old_open = prices[roll_index - 1]
        new_open = prices[roll_index]
        rolls.append(RollEvent(bars[roll_index].timestamp.date(), 'OLD', 'NEW', old_open, new_open,
                               new_open - old_open, (new_open / old_open - 1) * 100))
    specs = {name: FuturesContractSpec(name, 10, 1, 1_000, 2) for name in ('OLD', 'NEW')}
    return TqSdkBacktestDataset('TEST0', 'TEST', 'SYNTHETIC', bars[-1].timestamp, bars, rolls, specs)


def run(data, trends, triggers, variant='MA', chan=None, wyckoff=None, **settings):
    signals = [{'trend': side, 'strong': 0, 'trigger': triggers.get(i)}
               for i, side in enumerate(trends)]
    overlay = [{'chan': (chan or {}).get(i, 0), 'wyckoff': (wyckoff or {}).get(i, 0)}
               for i in range(len(trends))]
    return run_account(data, signals, overlay, data.bars[0].timestamp.date(),
                       data.bars[-1].timestamp.date(), variant, **settings)


def test_primary_add_and_reverse_on_the_next_observed_open():
    data = make_dataset([100, 101, 102, 103, 105, 104, 103])
    triggers = {0: 'LONG_CROSS', 1: 'LONG_REENTRY', 3: 'SHORT_CROSS'}
    trends = [1, 1, 1, -1, -1, -1, -1]
    result = run(data, trends, triggers)
    trades = result['trades']
    assert [(t['entryIndex'], t['exitIndex'], t['direction']) for t in trades] == [(1, 4, 1), (2, 4, 1), (4, 6, -1)]
    assert result['metrics']['addNetPnl'] == pytest.approx(6)
    assert result['metrics']['shortNetPnl'] == pytest.approx(-4)
    assert result['metrics']['netPnl'] == pytest.approx(18)
    assert result['metrics']['twoLotDays'] == 2
    no_add = run(data, trends, triggers, 'MA_NO_ADD')
    assert no_add['metrics']['addOpens'] == 0
    assert no_add['metrics']['primaryOpens'] == 2


def test_reverse_flattens_first_and_waits_for_short_overlay():
    data = make_dataset([100] * 7)
    result = run(data, [1, 1, -1, -1, -1, -1, -1], {0: 'LONG_CROSS', 2: 'SHORT_CROSS'},
                 'MA_CW', chan={0: 1, 4: -1}, wyckoff={0: 1, 4: -1})
    long, short = result['trades']
    assert (long['entryIndex'], long['exitIndex']) == (1, 3)
    assert (short['signalIndex'], short['approvalIndex'], short['entryIndex']) == (2, 4, 5)
    assert [bar['direction'] for bar in result['curve']] == [1, 1, 0, 0, -1, 0]


def test_roll_invalidates_gated_prior_close_for_a_new_open():
    data = make_dataset([100, 200, 200, 200, 200], roll_index=1)
    result = run(data, [1] * 5, {0: 'LONG_CROSS'}, 'MA_C', chan={0: 1, 2: 1})
    assert result['metrics']['denials']['GATED_OPEN_DEFERRED_ON_ROLL'] == 1
    trade, = result['trades']
    assert (trade['contract'], trade['approvalIndex'], trade['entryIndex'], trade['entryPrice']) == ('NEW', 2, 3, 201)


def test_roll_carries_existing_lots_but_roll_and_reverse_avoid_a_round_trip():
    data = make_dataset([100, 100, 100, 200, 200], roll_index=3)
    carry = run(data, [1] * 5, {0: 'LONG_CROSS', 1: 'LONG_REENTRY'})
    assert carry['metrics']['rollCloses'] == carry['metrics']['rollOpens'] == 2
    assert carry['metrics']['netPnl'] == pytest.approx(-96)

    reverse = run(data, [1, 1, -1, -1, -1], {0: 'LONG_CROSS', 2: 'SHORT_CROSS'})
    assert reverse['metrics']['rollCloses'] == reverse['metrics']['rollOpens'] == 0
    old, new = reverse['trades']
    assert (old['exitReason'], old['exitPrice'], new['entryReason'], new['entryPrice']) == ('MA_REVERSAL', 99, 'PRIMARY', 199)


def test_add_from_flat_is_primary_and_gate_only_add_preserves_main_reversal():
    data = make_dataset([100] * 7)
    result = run(data, [1, 1, 1, 1, -1, -1, -1], {0: 'LONG_REENTRY', 2: 'LONG_REENTRY', 4: 'SHORT_CROSS'},
                 'MA_CW_ADD')
    assert result['metrics']['primaryOpens'] == 2
    assert result['metrics']['addOpens'] == 0
    assert result['metrics']['denials']['SETUP_REPLACED'] == 1
    assert [trade['originTrigger'] for trade in result['trades']] == ['LONG_REENTRY', 'SHORT_CROSS']
