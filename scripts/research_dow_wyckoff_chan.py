"""Run the fixed, long-only daily futures exploration and write its audit JSON."""

from __future__ import annotations

import argparse
from bisect import bisect_left
from datetime import date, timedelta
from hashlib import sha256
from itertools import groupby, product
import json
from pathlib import Path
from statistics import mean, median
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backtesting.chanlun_research import detect, execute
from backtesting.independent_research import ResearchRisk, causal_prices
from data.tqsdk_backtest import TqSdkBacktestDataProvider


GROUPS = (('FU0', 'BU0', 'SC0'), ('RB0', 'HC0', 'I0'))
FAMILIES = ('RANGE_RETEST', 'CHAN_PEN_T3')
WINDOWS = {
    'all': (date(2019, 1, 1), date(2026, 11, 3)),
    '2019-2023': (date(2019, 1, 1), date(2023, 12, 31)),
    '2024-2025': (date(2024, 1, 1), date(2025, 12, 31)),
    '2026': (date(2026, 1, 1), date(2026, 11, 3)),
}
INITIAL_CASH = 1_000_000
VOLUME_LOOKBACK = 20
BREAKOUT_RVOL = 1.30
BREAKOUT_CLV = 0.65
MAX_RETEST_VOLUME_RATIO = 0.80
PIVOT_WIDTH = 2
MAX_PEER_WEEK_AGE = 14


def monday(day):
    return day - timedelta(days=day.weekday())


def weekly_trend(bars):
    """At each completed week, compare the two latest confirmed highs and lows."""
    weeks, closes = [], []
    for week, members in groupby(bars, key=lambda bar: monday(bar.timestamp.date())):
        weeks.append(week)
        closes.append(list(members)[-1].close)

    highs, lows, states = [], [], []
    for i, _ in enumerate(closes):
        if i >= 2 * PIVOT_WIDTH:
            middle = i - PIVOT_WIDTH
            value = closes[middle]
            neighbors = closes[middle - PIVOT_WIDTH:middle] + closes[middle + 1:i + 1]
            if value > max(neighbors):
                highs.append(value)
            elif value < min(neighbors):
                lows.append(value)
        state = 'MIXED'
        if len(highs) < 2 or len(lows) < 2:
            state = 'UNAVAILABLE'
        elif highs[-1] > highs[-2] and lows[-1] > lows[-2]:
            state = 'UP'
        elif highs[-1] < highs[-2] and lows[-1] < lows[-2]:
            state = 'DOWN'
        states.append(state)
    return weeks, states


def prior_week_state(tape, day):
    weeks, states = tape
    index = bisect_left(weeks, monday(day)) - 1
    if index < 0 or (monday(day) - weeks[index]).days > MAX_PEER_WEEK_AGE:
        return 'UNAVAILABLE'
    return states[index]


def price_anchors(event, bars, zones, ordered_pens, pen_indices):
    if event['source'] == 'RANGE_RETEST':
        return event['zoneId'], event['zoneId'] + 1

    index = pen_indices[event['pivotIndex'], event['confirmedIndex']]
    assert index > 0
    departure, pullback = ordered_pens[index - 1:index + 1]
    zone = zones[event['zoneId']]
    boundary = event['invalidation']
    assert departure['endIndex'] == pullback['startIndex']
    assert departure['startPrice'] <= boundary < departure['endPrice']
    assert departure['confirmedIndex'] <= event['confirmedIndex']
    first_observable = max(1, departure['startIndex'], zone['confirmedIndex'] + 1)
    for i in range(first_observable, departure['endIndex'] + 1):
        if bars[i - 1].close <= boundary < bars[i].close:
            return i, pullback['startIndex'] + 1
    return None, None


def volume_gate(bars, breakout, start_pullback, pivot):
    if breakout is None:
        return {'volumeStatus': 'NO_OBSERVED_BREAKOUT'}
    if breakout < VOLUME_LOOKBACK or not breakout < start_pullback <= pivot:
        return {'volumeStatus': 'NO_VOLUME_WINDOW'}
    bar = bars[breakout]
    span = bars[breakout - VOLUME_LOOKBACK:pivot + 1]
    if any(item.contract_symbol != bar.contract_symbol for item in span):
        return {'volumeStatus': 'VOLUME_WINDOW_STRADDLES_ROLL'}
    if bar.high <= bar.low or any(item.volume <= 0 for item in span):
        return {'volumeStatus': 'NO_VOLUME_WINDOW'}

    base = median(item.volume for item in bars[breakout - VOLUME_LOOKBACK:breakout])
    rvol = bar.volume / base
    clv = (bar.close - bar.low) / (bar.high - bar.low)
    retest_ratio = mean(item.volume for item in bars[start_pullback:pivot + 1]) / bar.volume
    passed = rvol >= BREAKOUT_RVOL and clv >= BREAKOUT_CLV and retest_ratio <= MAX_RETEST_VOLUME_RATIO
    return {'volumeStatus': 'PASS' if passed else 'BELOW_THRESHOLD',
            'rvol': rvol, 'clv': clv, 'retestRatio': retest_ratio}


def candidates(family, raw_bars, bars, peers):
    audit = detect(bars, family)
    zones = {zone['id']: zone for zone in audit['zones']}
    pens = audit['pens']
    pen_indices = {(pen['endIndex'], pen['confirmedIndex']): i for i, pen in enumerate(pens)}
    result = []
    for event in audit['events']:
        if event['direction'] != 1:
            continue
        confirmation = bars[event['confirmedIndex']].timestamp.date()
        pivot = event['pivotIndex']
        peer_states = {key: prior_week_state(tape, confirmation) for key, tape in peers.items()}
        detail = {}
        if family in FAMILIES:
            breakout, pullback = price_anchors(event, bars, zones, pens, pen_indices)
            detail = {**volume_gate(raw_bars, breakout, pullback, pivot),
                      'breakoutIndex': breakout, 'retestStartIndex': pullback}
        result.append({**event, **detail, 'date': confirmation.isoformat(), 'peerStates': peer_states,
                       'dowPass': all(state == 'UP' for state in peer_states.values())})
    return result


def score_window(data, bars, events, window, cost):
    result = execute(data, events, INITIAL_CASH, *window, cost_multiplier=cost, signal_bars=bars)
    curve = result['curve']
    rows = {row['date']: i for i, row in enumerate(curve)}
    trades = result['trades']
    assert all(trade['entryDate'] > trade['confirmedDate'] for trade in trades)
    assert len(trades) == sum(row['outcome'] == 'FILLED' for row in result['decisions'])
    holding_days = sum(rows[t['exitDate']] - rows[t['entryDate']] + 1 for t in trades)
    metrics = {**result['metrics'], 'scheduled': len(result['decisions']), 'holdingDays': holding_days,
               'totalR': sum(trade['rMultiple'] for trade in trades),
               'removeBestNetPnl': result['metrics']['netPnl'] - max((0, *(t['netPnl'] for t in trades)))}
    return metrics, curve


def combined(cases):
    metrics, curves = zip(*cases)
    days = [row['date'] for row in curves[0]]
    assert all([row['date'] for row in curve] == days for curve in curves), 'Calendar mismatch'
    peak = INITIAL_CASH * len(curves)
    drawdown = 0
    for points in zip(*curves):
        equity = sum(point['equity'] for point in points)
        peak = max(peak, equity)
        drawdown = max(drawdown, (peak - equity) / peak)
    n = sum(row['closedTrades'] for row in metrics)
    pnl = sum(row['netPnl'] for row in metrics)
    return {'trades': n, 'netPnl': pnl, 'returnPct': pnl / (INITIAL_CASH * len(curves)) * 100,
            'maxDrawdownPct': drawdown * 100, 'scheduled': sum(row['scheduled'] for row in metrics),
            'daysInPositionPct': sum(row['holdingDays'] for row in metrics) / (len(days) * len(curves)) * 100,
            'meanR': sum(row['totalR'] for row in metrics) / n if n else None,
            'positiveSymbols': sum(row['netPnl'] > 0 for row in metrics)}


def verify_prefixes(family, data, bars, peers, events):
    """A truncated tape may omit future events but must preserve published candidates."""
    stops = list(range(150, len(bars), 257))
    for stop in stops:
        prefix = bars[:stop]
        limit = monday(prefix[-1].timestamp.date())
        old_peers = {key: weekly_trend(bar for bar in peer if bar.timestamp.date() < limit)
                     for key, peer in peers.items()}
        result = candidates(family, data.bars[:stop], prefix, old_peers)
        assert result == [event for event in events if event['confirmedIndex'] < stop], (data.symbol, family, stop)
    return len(stops)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=ROOT / 'data/history/tqsdk-roll')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    provider = TqSdkBacktestDataProvider(cache_dir=args.input)
    datasets, prices, sources = {}, {}, {}
    for symbol in sum(GROUPS, ()):
        name = 'FU0_2018-07-14_end' if symbol == 'FU0' else symbol
        path = args.input / f'{name}_real_roll_daily.json'
        data = provider._read_cache(path, 0, allow_stale=True)
        if (not data or data.symbol != symbol or data.source != 'TQSDK_REAL_DOMINANT_DAILY'
                or not data.complete or len(data.bars) < 81):
            raise ValueError(f'Complete delivery-contract evidence required for {symbol}')
        if not data.bars[80].timestamp.date() <= WINDOWS['all'][0] <= WINDOWS['all'][1] <= data.bars[-1].timestamp.date():
            raise ValueError(f'{symbol} fails to cover the frozen scoring period')
        datasets[symbol] = data
        prices[symbol] = causal_prices(data)
        sources[symbol] = {'file': path.name, 'sha256': sha256(path.read_bytes()).hexdigest(),
                           'bars': len(data.bars), 'rolls': len(data.roll_events),
                           'first': data.bars[0].timestamp.date().isoformat(),
                           'last': data.bars[-1].timestamp.date().isoformat()}

    variants = list(product(FAMILIES, (False, True), (False, True)))
    variants.append(('CHANNEL_BREAKOUT', False, False))
    weekly = {symbol: weekly_trend(bars) for symbol, bars in prices.items()}
    events, runs, aggregates, checks = {}, [], {}, 0
    for group in GROUPS:
        for symbol in group:
            peer_bars = {key: prices[key] for key in group if key != symbol}
            peers = {key: weekly[key] for key in peer_bars}
            events[symbol] = {}
            for family in (*FAMILIES, 'CHANNEL_BREAKOUT'):
                tape = candidates(family, datasets[symbol].bars, prices[symbol], peers)
                checks += verify_prefixes(family, datasets[symbol], prices[symbol], peer_bars, tape)
                events[symbol][family] = tape

    symbols = sum(GROUPS, ())
    for family, trend, volume in variants:
        label = f'{family}:D{int(trend)}:W{int(volume)}'
        aggregates[label] = {}
        for (period, window), cost in product(WINDOWS.items(), (1, 2)):
            cases = []
            for symbol in symbols:
                selected = [e for e in events[symbol][family]
                            if (not trend or e['dowPass']) and (not volume or e['volumeStatus'] == 'PASS')]
                metrics, curve = score_window(datasets[symbol], prices[symbol], selected, window, cost)
                runs.append({'variant': label, 'symbol': symbol, 'period': period, 'cost': cost, **metrics})
                cases.append((metrics, curve))
            aggregates[label][f'{period}@{cost}x'] = {
                'all': combined(cases), 'energy': combined(cases[:3]), 'ferrous': combined(cases[3:])}

    start, end = (day.isoformat() for day in WINDOWS['all'])
    in_period = {symbol: {family: [e for e in tape if start <= e['date'] <= end]
                          for family, tape in tapes.items()} for symbol, tapes in events.items()}
    code_files = (Path(__file__).resolve(), ROOT / 'backtesting/chanlun_research.py',
                  ROOT / 'backtesting/independent_research.py', ROOT / 'backtesting/backtester.py',
                  ROOT / 'data/tqsdk_backtest.py')
    payload = {'status': 'HISTORICAL_EXPLORATION', 'sources': sources, 'groups': GROUPS,
               'windows': {name: [day.isoformat() for day in window] for name, window in WINDOWS.items()},
               'sourceHashes': {str(path.relative_to(ROOT)).replace('\\', '/'): sha256(path.read_bytes()).hexdigest()
                                for path in code_files},
               'risk': vars(ResearchRisk()), 'initialCashPerSymbol': INITIAL_CASH,
               'candidatePrefixChecks': checks, 'candidates': in_period, 'runs': runs, 'aggregates': aggregates}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as output:
        json.dump(payload, output, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
        output.write('\n')
    print(f'{len(runs)} account runs, {checks} prefix checks -> {args.output}')


if __name__ == '__main__':
    main()
