"""Backtest the user's daily MA reversal and long add rule with Chan/Wyckoff overlays."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
from itertools import product
import json
from pathlib import Path
from statistics import mean, median
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backtesting.independent_research import causal_prices
from backtesting.personal_ma_execution import VARIANTS, run_account
from backtesting.personal_ma_overlay import overlay_tape
from backtesting.personal_ma_signals import ma_tape
from scripts.research_dow_wyckoff_chan import GROUPS, WINDOWS
from scripts.theory_matrix_daily import load_snapshots


WAIT_BARS = 10
VALIDITY_BARS = 10


def combine(results):
    curves = [result['curve'] for result in results]
    dates = [point['date'] for point in curves[0]]
    if not dates or any([point['date'] for point in curve] != dates for curve in curves):
        raise ValueError('Cannot combine unmatched account calendars')
    rows = [result['metrics'] for result in results]
    initial = sum(row['initialCash'] for row in rows)
    peak = initial
    drawdown = 0.0
    for points in zip(*curves):
        equity = sum(point['equity'] for point in points)
        peak = max(peak, equity)
        drawdown = max(drawdown, (peak - equity) / peak)
    pnl = sum(row['netPnl'] for row in rows)
    fields = ('closedTrades', 'strategyClosures', 'rollCloses', 'rollOpens', 'terminalCloses', 'longCloses', 'shortCloses',
              'primaryOpens', 'addOpens', 'longOpenSignals', 'shortOpenSignals', 'fees', 'slippageCost',
              'daysInPosition', 'longDays', 'shortDays', 'twoLotDays', 'strongPositionDays',
              'longNetPnl', 'shortNetPnl', 'addNetPnl')
    sums = {key: sum(row[key] for row in rows) for key in fields}
    return {**sums, 'initialCash': initial, 'netPnl': pnl, 'returnPct': pnl / initial * 100,
            'maxDrawdownPct': drawdown * 100,
            'exposurePct': sums['daysInPosition'] * 100 / (len(dates) * len(rows)),
            'positiveSymbols': sum(row['netPnl'] > 0 for row in rows),
            'denials': dict(sum((Counter(row['denials']) for row in rows), Counter()))}


def output_strength(observations):
    return {key: {'observations': len(values), 'meanSignedReturnPct': mean(values),
                  'medianSignedReturnPct': median(values),
                  'positiveFrequencyPct': sum(value > 0 for value in values) / len(values) * 100}
            for key, values in sorted(observations.items())}


def collect_strength(observations, dataset, signals):
    """Measure subsequent direction-aligned moves from today's close for descriptive audit."""
    start, end = WINDOWS['all']
    bars = dataset.bars
    for i, (bar, signal) in enumerate(zip(bars, signals)):
        trend = signal['trend']
        if trend == 0 or not start <= bar.timestamp.date() <= end:
            continue
        side = 'long' if trend > 0 else 'short'
        strength = 'strong' if signal['strong'] == trend else 'ordinary'
        for horizon in (1, 5):
            j = i + horizon
            if j >= len(bars) or bars[j].timestamp.date() > end:
                continue
            if any(following.contract_symbol != bar.contract_symbol for following in bars[i + 1:j + 1]):
                continue
            change = trend * (bars[j].close / bar.close - 1) * 100
            observations[f'{side}:{strength}:{horizon}d'].append(change)


def inspect_inputs(input_dir):
    datasets, sources = load_snapshots(input_dir)
    tapes, signal_counts, prefix_checks = {}, {}, 0
    observations = defaultdict(list)
    start, end = WINDOWS['all']
    for symbol, dataset in datasets.items():
        prices = causal_prices(dataset)
        signals, overlay = ma_tape(prices), overlay_tape(prices, dataset.bars, validity_bars=VALIDITY_BARS)
        for stop in range(135, len(prices), 233):
            prefix = prices[:stop]
            if signals[:stop] != ma_tape(prefix):
                raise AssertionError(f'{symbol}: MA history changed at {stop}')
            if overlay[:stop] != overlay_tape(prefix, dataset.bars[:stop], validity_bars=VALIDITY_BARS):
                raise AssertionError(f'{symbol}: structure and volume history changed at {stop}')
            prefix_checks += 1
        tapes[symbol] = signals, overlay
        selected = [i for i, bar in enumerate(dataset.bars) if start <= bar.timestamp.date() <= end]
        signal_counts[symbol] = {
            'triggers': dict(Counter(signals[i]['trigger'] for i in selected if signals[i]['trigger'])),
            'chanActiveSessions': dict(Counter(str(overlay[i]['chan']) for i in selected)),
            'wyckoffActiveSessions': dict(Counter(str(overlay[i]['wyckoff']) for i in selected)),
            'sameDirectionOverlaySessions': dict(Counter(str(overlay[i]['chan']) for i in selected
                                                         if overlay[i]['chan'] == overlay[i]['wyckoff'] != 0)),
        }
        collect_strength(observations, dataset, signals)
    return datasets, sources, tapes, signal_counts, prefix_checks, output_strength(observations)


def run_research(input_dir):
    datasets, sources, tapes, signal_counts, prefix_checks, strength = inspect_inputs(input_dir)
    runs, summary = [], {}
    for variant, (period, window), cost in product(VARIANTS, WINDOWS.items(), (1, 2)):
        results = []
        for symbol, dataset in datasets.items():
            signals, overlay = tapes[symbol]
            result = run_account(dataset, signals, overlay, *window, variant,
                                 cost_multiplier=cost, wait_bars=WAIT_BARS)
            runs.append({'variant': variant, 'window': period, 'cost': cost, 'symbol': symbol,
                         'metrics': result['metrics'], 'trades': result['trades'], 'decisions': result['decisions']})
            results.append(result)
        without_sc = [result for symbol, result in zip(datasets, results) if symbol != 'SC0']
        summary.setdefault(variant, {})[f'{period}@{cost}x'] = {
            'all': combine(results), 'energy': combine(results[:3]), 'ferrous': combine(results[3:]),
            'withoutSC': combine(without_sc),
        }

    files = ('scripts/research_personal_ma.py', 'scripts/theory_matrix_daily.py',
             'scripts/research_dow_wyckoff_chan.py', 'backtesting/personal_ma_signals.py',
             'backtesting/personal_ma_overlay.py', 'backtesting/personal_ma_execution.py',
             'backtesting/chanlun_research.py', 'backtesting/independent_research.py',
             'backtesting/backtester.py', 'data/tqsdk_backtest.py')
    return {'status': 'HISTORICAL_EXPLORATION', 'groups': GROUPS, 'sources': sources,
            'windows': {name: [day.isoformat() for day in window] for name, window in WINDOWS.items()},
            'confirmationWaitBars': WAIT_BARS, 'overlayValidityBars': VALIDITY_BARS,
            'prefixChecks': prefix_checks, 'sourceHashes': {file: sha256((ROOT / file).read_bytes()).hexdigest()
                                                            for file in files},
            'signalCounts': signal_counts, 'strength': strength, 'summary': summary, 'runs': runs}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=ROOT / 'data/history/tqsdk-roll')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Choose a fresh output file')
    result = run_research(args.input)
    with args.output.open('x', encoding='utf-8') as file:
        json.dump(result, file, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
        file.write('\n')
    print(f"{len(result['runs'])} account simulations, {result['prefixChecks']} prefix checks -> {args.output}")


if __name__ == '__main__':
    main()
