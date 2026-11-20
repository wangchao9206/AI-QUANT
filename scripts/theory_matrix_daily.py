"""Run the daily SMA and theory matrix on six actual-contract snapshots."""

from hashlib import sha256
from itertools import product
from pathlib import Path

from backtesting.independent_research import causal_prices
from backtesting.theory_matrix import variants
from data.tqsdk_backtest import TqSdkBacktestDataProvider
from scripts.research_dow_wyckoff_chan import (
    GROUPS,
    INITIAL_CASH,
    WINDOWS,
    combined,
    monday,
    prior_week_state,
    score_window,
    weekly_trend,
)


MA_PERIODS = {'NONE': None, 'MA5': 5, 'MA10': 10, 'MA20': 20}
THEORIES = ('BASE', 'D', 'W', 'C', 'DW', 'DC', 'WC', 'DWC')


def load_snapshots(input_dir):
    provider = TqSdkBacktestDataProvider(cache_dir=input_dir)
    snapshots, sources = {}, {}
    start, end = WINDOWS['all']
    for symbol in sum(GROUPS, ()):
        stem = 'FU0_2018-07-14_end' if symbol == 'FU0' else symbol
        path = input_dir / f'{stem}_real_roll_daily.json'
        snapshot = provider._read_cache(path, 0, allow_stale=True)
        if (not snapshot or snapshot.symbol != symbol or not snapshot.complete
                or snapshot.source != 'TQSDK_REAL_DOMINANT_DAILY' or len(snapshot.bars) < 81):
            raise ValueError(f'Incomplete actual-contract daily data for {symbol}: {path}')
        if snapshot.bars[80].timestamp.date() > start or snapshot.bars[-1].timestamp.date() < end:
            raise ValueError(f'{symbol} does not cover the scoring period and its warmup')
        scored = [bar for bar in snapshot.bars if start <= bar.timestamp.date() <= end]
        sources[symbol] = {
            'file': path.name,
            'sha256': sha256(path.read_bytes()).hexdigest(),
            'bars': len(snapshot.bars),
            'scoredBars': len(scored),
            'zeroVolumeBars': sum(bar.volume <= 0 for bar in scored),
            'flatBars': sum(bar.high == bar.low for bar in scored),
            'rolls': len(snapshot.roll_events),
            'first': snapshot.bars[0].timestamp.date().isoformat(),
            'last': snapshot.bars[-1].timestamp.date().isoformat(),
        }
        snapshots[symbol] = snapshot
    return snapshots, sources


def dow_up_on_days(bars, peer_tapes):
    return [all(prior_week_state(tape, bar.timestamp.date()) == 'UP' for tape in peer_tapes)
            for bar in bars]


def verify_prefixes(symbol, bars, raw_bars, peer_bars, ma_period, tape):
    stops = (200, len(bars) // 2, len(bars) - 20)
    for stop in stops:
        prefix = bars[:stop]
        week_limit = monday(prefix[-1].timestamp.date())
        peer_tapes = [weekly_trend(bar for bar in peer if bar.timestamp.date() < week_limit)
                      for peer in peer_bars]
        truncated = variants(prefix, raw_bars[:stop], dow_up_on_days(prefix, peer_tapes), ma_period=ma_period)
        for theory in THEORIES:
            expected = [event for event in tape[theory] if event['confirmedIndex'] < stop]
            if truncated[theory] != expected:
                raise AssertionError(f'Revised daily signals for {symbol}, MA={ma_period}, {theory}, stop={stop}')
    return len(stops)


def in_window_count(events, bars, window):
    start, end = window
    return sum(start <= bars[e['confirmedIndex']].timestamp.date() <= end for e in events)


def run_daily(input_dir: Path) -> dict:
    snapshots, sources = load_snapshots(input_dir)
    prices = {symbol: causal_prices(snapshot) for symbol, snapshot in snapshots.items()}
    weekly = {symbol: weekly_trend(bars) for symbol, bars in prices.items()}

    tapes, checks = {}, 0
    for group in GROUPS:
        for symbol in group:
            bars = prices[symbol]
            raw_bars = snapshots[symbol].bars
            peers = [peer for peer in group if peer != symbol]
            dow_up = dow_up_on_days(bars, [weekly[peer] for peer in peers])
            tapes[symbol] = {}
            for tag, period in MA_PERIODS.items():
                tape = variants(bars, raw_bars, dow_up, ma_period=period)
                if set(tape) != set(THEORIES):
                    raise AssertionError(f'Incomplete theory matrix for {symbol}, {tag}')
                if any(event['direction'] != 1 for events in tape.values() for event in events):
                    raise AssertionError(f'Non-long candidate for {symbol}, {tag}')
                checks += verify_prefixes(symbol, bars, raw_bars, [prices[peer] for peer in peers], period, tape)
                # Isolate entry rules. Positive prices never reach the shared zero boundary.
                tapes[symbol][tag] = {name: [{**e, 'invalidation': 0.0} for e in events]
                                      for name, events in tape.items()}

    aggregates, runs = {}, []
    for tag, theory in product(MA_PERIODS, THEORIES):
        grid = aggregates.setdefault(tag, {}).setdefault(theory, {})
        for (name, window), cost in product(WINDOWS.items(), (1, 2)):
            cases = []
            for symbol, snapshot in snapshots.items():
                bars = prices[symbol]
                events = tapes[symbol][tag][theory]
                metrics, curve = score_window(snapshot, bars, events, window, cost)
                candidates = in_window_count(events, bars, window)
                metrics['confirmedCandidates'] = candidates
                runs.append({'ma': tag, 'theory': theory, 'period': name, 'cost': cost,
                             'symbol': symbol, **metrics})
                cases.append((metrics, curve))
            grid[f'{name}@{cost}x'] = {}
            for label, subset in (('all', cases), ('energy', cases[:3]), ('ferrous', cases[3:])):
                grid[f'{name}@{cost}x'][label] = {
                    **combined(subset),
                    'confirmedCandidates': sum(metrics['confirmedCandidates'] for metrics, _ in subset),
                }

    return {
        'status': 'HISTORICAL_EXPLORATION',
        'sources': sources,
        'groups': GROUPS,
        'windows': {name: [day.isoformat() for day in window] for name, window in WINDOWS.items()},
        'initialCashPerSymbol': INITIAL_CASH,
        'maPeriods': MA_PERIODS,
        'candidatePrefixChecks': checks,
        'aggregateSettings': {'directions': ['LONG'], 'structureExits': False},
        'runs': runs,
        'aggregates': aggregates,
    }
