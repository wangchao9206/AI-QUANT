from dataclasses import replace
from datetime import datetime, timedelta, timezone

from backtesting import theory_matrix
from data.data_feed import KLineBar


def sample_bars(closes):
    origin = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [KLineBar(origin + timedelta(days=i), price, price + 1, price - 1,
                     price, 100, 0, 'TEST1') for i, price in enumerate(closes)]


def test_dow_requires_both_higher_swings_and_right_bar_confirmation():
    bars = sample_bars([5, 6, 9, 7, 5, 4, 6, 8, 11, 8, 7, 6, 8, 10])
    assert theory_matrix.dow_structure_up(bars) == [False] * 13 + [True]
    assert not any(theory_matrix.dow_structure_up(bars[:-1]))


def test_ma_cross_is_a_baseline_and_ma_state_gates_a_later_chan_event(monkeypatch):
    bars = sample_bars([10, 10, 10, 10, 10, 12, 11, 8, 9, 13])
    chan = {i: theory_matrix.event_at(i, 'CHAN_PEN_T3') for i in (6, 7)}
    monkeypatch.setattr(theory_matrix, 'events_by_index',
                        lambda bars, family: chan if family == 'CHAN_PEN_T3' else {})
    results = theory_matrix.variants(bars, bars, [False] * len(bars), ma_period=5)
    assert [event['confirmedIndex'] for event in results['BASE']] == [5, 9]
    assert [event['confirmedIndex'] for event in results['C']] == [6]


def test_wyckoff_setup_combines_only_after_confirmation_and_before_support_break(monkeypatch):
    bars = sample_bars([103] * 33)
    bars[22] = replace(bars[22], open=101, low=100, high=104, volume=160)
    bars[28] = replace(bars[28], low=100)
    retest = {25: {**theory_matrix.event_at(25, 'RANGE_RETEST'), 'zoneId': 22, 'invalidation': 100}}
    chan = {i: theory_matrix.event_at(i, 'CHAN_PEN_T3') for i in (24, 25, 26, 27, 29)}
    monkeypatch.setattr(theory_matrix, 'events_by_index',
                        lambda bars, family: chan if family == 'CHAN_PEN_T3' else retest)
    dow = [i >= 23 for i in range(len(bars))]
    results = theory_matrix.variants(bars, bars, dow, wyckoff_setup_bars=1)
    assert [event['confirmedIndex'] for event in results['D']] == [23]
    assert [event['confirmedIndex'] for event in results['W']] == [25]
    assert [event['confirmedIndex'] for event in results['DW']] == [25]
    assert [event['confirmedIndex'] for event in results['DWC']] == [25, 26]
    unexpired = theory_matrix.variants(bars, bars, dow, wyckoff_setup_bars=10)
    assert [event['confirmedIndex'] for event in unexpired['WC']] == [25, 26, 27]
    raw = bars.copy()
    raw[11] = replace(raw[11], contract_symbol='OLDER')
    assert not theory_matrix.variants(bars, raw, dow)['W']
