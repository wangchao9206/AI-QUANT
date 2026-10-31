"""Causality and execution evidence, using synthetic shapes rather than return targets."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from backtesting.chanlun_research import (
    SegmentBuilder, Unit, ZoneMachine, detect, execute, identify_pens,
)
from backtesting.independent_research import ResearchRisk, causal_prices
from data.data_feed import KLineBar
from data.tqsdk_backtest import FuturesContractSpec, RollEvent, TqSdkBacktestDataset


def bars(values):
    return [KLineBar(datetime(2020, 1, 1, tzinfo=timezone.utc) + timedelta(days=i),
                    p, p + 2, p - 2, p, 100_000, 100_000, 'FU2005')
            for i, p in enumerate(values)]


def units(points, confirmations=None):
    return [Unit(i, i + 1, a, b, confirmations[i] if confirmations else i + 2)
            for i, (a, b) in enumerate(zip(points, points[1:]))]


def dataset(values):
    b = bars(values)
    return TqSdkBacktestDataset('FU0', 'TEST', 'SYNTHETIC', b[-1].timestamp, b, [],
                               {'FU2005': FuturesContractSpec('FU2005', 10, 1, 1000, 2)}, True, b)


def event(i=80, direction=1, boundary=80):
    return {'direction': direction, 'pivotIndex': i - 3, 'confirmedIndex': i,
            'zoneLower': boundary - 5, 'zoneUpper': boundary,
            'invalidation': boundary, 'source': 'TEST', 'zoneId': 1}


def test_pen_endpoints_are_only_published_after_the_following_opposite_turn():
    b = bars([100, 102, 104, 106, 108, 110, 108, 106, 104, 102, 100,
              102, 104, 106, 108, 112, 110, 108, 106, 104, 102, 100, 98,
              100, 102, 104, 106, 108, 110, 112, 114, 112, 110, 108])
    full, _ = identify_pens(b)
    assert len(full) >= 2
    assert all(p.confirmedIndex > p.endIndex > p.startIndex for p in full)
    for n in range(1, len(b) + 1):
        prefix, _ = identify_pens(b[:n])
        assert prefix == [p for p in full if p.confirmedIndex < n]


def test_inclusions_and_equal_ranges_do_not_emit_fake_fractals():
    b = bars([100] * 40)
    assert identify_pens(b)[0] == []
    b[1].high, b[1].low = 100.1, 99.9
    assert identify_pens(b)[0] == []


def test_segment_without_feature_gap_confirms_at_observed_time():
    builder = SegmentBuilder()
    result = []
    for u in units([0, 5, 2, 8, 3, 7, 1]):
        result.extend(builder.push(u))
    assert result and result[0].startPrice == 0 and result[0].endPrice == 8
    assert result[0].confirmedIndex > result[0].endIndex


def test_gapped_segment_waits_for_opposite_feature_fractal():
    builder = SegmentBuilder()
    result = []
    for u in units([0, 5, 2, 10, 7, 9, 6, 8, 4]):
        result.extend(builder.push(u))
    assert result == []
    for u in units([0, 5, 2, 10, 7, 9, 6, 8, 4, 7, 5, 8])[8:]:
        result.extend(builder.push(u))
    assert result and result[0].endPrice == 10


@pytest.mark.parametrize('sign', [1, -1])
def test_zone_signal_is_at_pullback_confirmation_and_strictly_outside(sign):
    # First three ranges intersect at [102,110]; leave to120, pull back112.
    points = [100, 110, 102, 108, 120, 112]
    # Units must alternate: center units are up/down/up, departure is the
    # next up unit after an extending downward swing inside the center.
    points = [100, 110, 102, 108, 104, 120, 112]
    transformed = [300 + sign * p for p in points]
    b = bars([300 + sign * 115] * 30)
    machine = ZoneMachine(b, 'TEST')
    observed = []
    for u in units(transformed, [3, 5, 7, 9, 11, 15]):
        observed.extend(machine.push(u))
    assert len(observed) == 1
    assert observed[0]['direction'] == sign
    assert observed[0]['confirmedIndex'] == 15
    assert observed[0]['pivotIndex'] == 6


def test_touching_center_or_later_crossing_before_confirmation_cancels_signal():
    b = bars([115] * 30)
    for points in ([100, 110, 102, 108, 104, 120, 108],
                   [100, 110, 102, 108, 104, 120, 112]):
        machine = ZoneMachine(b, 'TEST')
        if points[-1] == 112:
            b[12].low = 105
        observed = []
        for u in units(points, [3, 5, 7, 9, 11, 15]):
            observed.extend(machine.push(u))
        assert observed == []


def test_all_detectors_are_prefix_invariant_and_price_mirror_symmetric():
    import math
    b = bars([100 + i * .03 + 7 * math.sin(i / 4) + 3 * math.sin(i / 13) for i in range(220)])
    for family in ('CHAN_SEGMENT_T3', 'CHAN_PEN_T3', 'RANGE_RETEST', 'CHANNEL_BREAKOUT'):
        full = detect(b, family)
        for n in (70, 110, 150, 190):
            prefix = detect(b[:n], family)
            assert prefix['events'] == [e for e in full['events'] if e['confirmedIndex'] < n]
        changed = deepcopy(b)
        for x in changed[150:]:
            x.open *= 2; x.high *= 2; x.low *= 2; x.close *= 2
        assert [e for e in detect(changed, family)['events'] if e['confirmedIndex'] < 150] == [
            e for e in full['events'] if e['confirmedIndex'] < 150]


def test_next_open_fill_and_account_cash_reconcile_with_round_trip_fees():
    d = dataset([100] * 85)
    d.bars[81].open, d.bars[81].high, d.bars[81].low = 103, 130, 90
    result = execute(d, [event()], 1_000_000, d.bars[80].timestamp.date(), d.bars[-1].timestamp.date())
    t = result['trades'][0]
    assert t['entryDate'] == d.bars[81].timestamp.date().isoformat()
    assert t['entryPrice'] == 104 and t['exitReason'] == 'STOP'
    assert t['pivotDate'] < t['confirmedDate'] < t['entryDate']
    assert result['metrics']['netPnl'] == pytest.approx(sum(x['netPnl'] for x in result['trades']))


def test_small_account_gap_and_delayed_invalid_signal():
    d = dataset([100] * 87)
    small = execute(d, [event()], 10, d.bars[80].timestamp.date(), d.bars[-1].timestamp.date())
    assert small['metrics']['closedTrades'] == 0
    d.bars[82].open = 60; d.bars[82].low = 59
    normal = execute(d, [event()], 1e6, d.bars[80].timestamp.date(), d.bars[-1].timestamp.date())
    assert normal['metrics']['overBudgetExits'] == 1
    delayed = execute(d, [event()], 1e6, d.bars[80].timestamp.date(), d.bars[-1].timestamp.date(), delay=1)
    assert delayed['metrics']['closedTrades'] == 0
    assert delayed['metrics']['denials']['STRUCTURE_INVALID_AT_OPEN'] == 1


def test_delivery_roll_closes_old_contract_and_cancels_new_order():
    d = dataset([100] * 87)
    for b in d.bars[82:]:
        b.open *= 2; b.high *= 2; b.low *= 2; b.close *= 2; b.contract_symbol = 'FU2009'
    d = replace(d, contract_specs={**d.contract_specs, 'FU2009': FuturesContractSpec('FU2009', 10, 1, 1000, 2)},
                roll_events=[RollEvent(d.bars[82].timestamp.date(), 'FU2005', 'FU2009', 100, 200, 100, 100)])
    result = execute(d, [event(), event(81)], 1e6, d.bars[80].timestamp.date(), d.bars[-1].timestamp.date())
    assert result['trades'][0]['exitReason'] == 'ROLL_EXIT'
    assert result['trades'][0]['contract'] == 'FU2005'
    assert result['metrics']['denials']['ROLL_DAY_NEW_ORDER_CANCELLED'] == 1
    assert causal_prices(d)[82].close == 100


def test_completed_execution_window_ignores_all_future_observations():
    d = dataset([100] * 100)
    altered = deepcopy(d)
    for b in altered.bars[90:]:
        b.open *= 2; b.high *= 2; b.low *= 2; b.close *= 2
    start, end = d.bars[80].timestamp.date(), d.bars[87].timestamp.date()
    assert execute(d, [event()], 1e6, start, end) == execute(altered, [event()], 1e6, start, end)
