"""Backtest half-size daily MA with independent 15/30/60 minute triggers."""

from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import date, datetime, time, timedelta
from hashlib import sha256
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backtesting.personal_ma_multiframe_execution import run_multiframe_account
from backtesting.personal_ma_multiframe_signals import minute_events
from backtesting.personal_ma_signals import ma_tape
from data.data_feed import KLineBar
from data.intraday_replay import aggregate as aggregate_archived_minutes
from data.tqsdk_backtest import FuturesContractSpec
from scripts.fg701_daily_macd import SH, current_contract_daily, verify_daily_overlap
from scripts.theory_matrix_intraday import _load as load_verified_glass


HISTORY = ROOT / 'data/history'
ORIGINAL_WINDOW = (date(2026, 10, 19), date(2026, 11, 16))
MULTI_WINDOW = (date(2026, 9, 10), date(2026, 11, 16))
PERIODS = (15, 30, 60)
FAMILIES = ('chan', 'wyckoff', 'either')
CONTRACTS = ('FG701', 'SA701', 'AP701', 'CJ701')
SPLIT = ('MINUTE_ADD', 'MA10_ADD')


def sdk_stamp(row):
    return datetime.fromtimestamp(row['datetime'] / 1e9, SH)


def sdk_bar(row, symbol):
    return KLineBar(sdk_stamp(row), row['open'], row['high'], row['low'], row['close'],
                    int(row['volume']), int(row.get('close_oi') or 0), symbol)


def sdk_spec(symbol, history=HISTORY):
    catalog = json.loads((history / f'tqsdk-roll/{symbol[:2]}0_real_roll_daily.json').read_bytes())
    attributes = catalog['contract_specs'][symbol]
    if symbol == 'FG701':
        # Use the earlier FG replay expense convention in both evidence windows.
        attributes = {**attributes, 'commission_per_lot': 6.0}
    return FuturesContractSpec(**attributes)


def score(rows, day_by_bar, sessions, cadence, daily_rows, spec, window):
    start, end = window
    events = minute_events(rows, day_by_bar, sessions, cadence)
    daily_signals = {bar.timestamp.date(): signal for bar, signal in zip(daily_rows, ma_tape(daily_rows))}
    if not any(signal['trend'] for day, signal in daily_signals.items() if day < start):
        raise ValueError('Missing daily SMA warmup')
    prefix_ok = 0
    for length in range(96, len(rows), max(len(rows) // 4, 96)):
        prefix = minute_events(rows[:length], day_by_bar[:length], sessions, cadence)
        cutoff = rows[length - 1].timestamp + timedelta(minutes=cadence)
        for period in PERIODS:
            for family in FAMILIES:
                expected = {stamp: side for stamp, side in events[period][family].items() if stamp <= cutoff}
                if prefix[period][family] != expected:
                    raise AssertionError('Previously available minute signal was revised after append')
        prefix_ok += 1

    scope = {'first': start.isoformat(), 'last': end.isoformat(), 'nativeMinutes': cadence,
             'scoreDays': len({day for day in day_by_bar if start <= day <= end}),
             'scoreNativeBars': sum(start <= day <= end for day in day_by_bar), 'prefixChecks': prefix_ok}
    coverage = {}
    for period in PERIODS:
        tape = events[period]
        by_time = tape['scoringDaysByTime']
        coverage[str(period)] = {'bars': sum(start <= day <= end for day in by_time.values()),
                                 **{family: dict(Counter(str(side) for stamp, side in tape[family].items()
                                                        if start <= by_time[stamp] <= end))
                                    for family in FAMILIES}}
    configurations = [('MA', None, False, False), ('MA_NO_ADD', None, True, False)]
    scoring_days = [day for day in day_by_bar if start <= day <= end]
    for period in PERIODS:
        for family in FAMILIES:
            for policy in SPLIT:
                configurations.append((f'{period}:{family}:{policy}', events[period][family], False,
                                       policy == 'MINUTE_ADD'))
    results = {}
    for label, confirmations, no_add, minute_add in configurations:
        results[label] = {}
        for cost in (1, 2):
            result = run_multiframe_account(rows, day_by_bar, daily_signals, spec, start, end,
                                            confirmations=confirmations, no_add=no_add, minute_add=minute_add,
                                            cost_multiplier=cost)
            equity = {day.isoformat(): mark['equity'] for day, mark in zip(scoring_days, result['curve'], strict=True)}
            results[label][str(cost)] = {**{key: result[key] for key in ('metrics', 'trades')}, 'dailyEquity': equity}
    triggers = {day.isoformat(): signal['trigger'] for day, signal in daily_signals.items()
                if start <= day <= end and signal['trigger']}
    return {'scope': scope, 'coverage': coverage, 'results': results, 'spec': asdict(spec), 'dailyTriggers': triggers}


def audited_glass(window):
    original = HISTORY / 'fg701-intraday-2026-11-17/raw.json'
    daily_path = HISTORY / 'fg701-macd-daily-2026-11-17/raw.json'
    archive = HISTORY / 'intraday-replay/FG701.json'
    raw = json.loads(original.read_bytes())
    daily = json.loads(daily_path.read_bytes())
    audit = verify_daily_overlap(raw, daily)
    current, era = current_contract_daily(daily['daily'], raw['spec']['expire_datetime'])
    prices = [sdk_bar(row, 'FG701') for row in current if sdk_stamp(row).date() <= window[1]]
    bars, days, sessions, spec, provenance = load_verified_glass(archive, original)
    result = score(bars, days, sessions, 1, prices, spec, window)
    return {**result, 'source': {**provenance, 'dailyFileSha256': sha256(daily_path.read_bytes()).hexdigest(),
                                 'parallelDailyCheck': audit, 'dailyEra': era}}


def clock_range(first, last):
    a, b = (time.fromisoformat(clock) for clock in (first, last))
    return {time(index // 60, index % 60) for index in range(a.hour * 60 + a.minute, b.hour * 60 + b.minute, 15)}


def validated_sdk_inputs(data, symbol, window, *, history=HISTORY):
    raw = data['contracts'][symbol]
    if (data['nativeMinutes'] != 15 or raw['contract'] != symbol or raw['providerSymbol'] != f'CZCE.{symbol}'):
        raise ValueError('Unexpected SDK source identity')
    spec = sdk_spec(symbol, history)
    if (raw['tick'], raw['multiple']) != (spec.price_tick, spec.volume_multiple):
        raise ValueError(f'{symbol} contract specification differs')
    current, era = current_contract_daily(raw['daily'], raw['expiry'])
    calendar = [date.fromisoformat(day) for day in data['tradingDates']]
    start, end = window
    if (not calendar or calendar[0] > start or calendar[-1] < end
            or any(previous >= following for previous, following in zip(calendar, calendar[1:]))):
        raise ValueError('The dated trading calendar is missing, disordered or shorter than the replay window')
    daily = [sdk_bar(row, symbol) for row in current if sdk_stamp(row).date() <= end]
    references = {bar.timestamp.date(): bar for bar in daily}
    core = set.union(*(clock_range(*session) for session in raw['sessions']['day']))
    night = set().union(*(clock_range(*session) for session in raw['sessions']['night']))
    by_day = defaultdict(list)
    minutes = raw['minutes'][:-1] if data.get('lastBarsMayBeProvisional') else raw['minutes']
    for row in minutes:
        bar = sdk_bar(row, symbol)
        stamp = bar.timestamp
        index = bisect_right(calendar, stamp.date())
        if stamp.time() in night:
            if index == len(calendar):
                continue
            day = calendar[index]
        else:
            day = stamp.date()
        if day <= end and day in references:
            by_day[day].append(bar)
    completed, failures = {}, {}
    for day, bars in sorted(by_day.items()):
        session = [bar.timestamp.time() for bar in bars]
        times = set(session)
        day_bar = references[day]
        expected = (day_bar.open, day_bar.high, day_bar.low, day_bar.close, day_bar.volume)
        actual = (bars[0].open, max(bar.high for bar in bars), min(bar.low for bar in bars),
                  bars[-1].close, sum(bar.volume for bar in bars))
        if times not in (core, core | night) or len(times) != len(session) or actual != expected:
            failures[day.isoformat()] = {'bars': len(bars), 'expectedOHLCV': expected, 'actualOHLCV': actual}
        else:
            completed[day] = bars
    calendar_window = {day for day in calendar if start <= day <= end}
    if not calendar_window:
        raise ValueError('The requested replay window contains no verified trading days')
    if missing := sorted(calendar_window - completed.keys()):
        raise ValueError(f'{symbol}: {len(missing)} incomplete score days starting {missing[0]}. Details: {failures.get(missing[0].isoformat())}')
    first_complete = min(completed)
    ordered = [day for day in calendar if first_complete <= day <= end]
    earlier_gaps = [i for i, day in enumerate(ordered) if day not in completed]
    selected = ordered[earlier_gaps[-1] + 1:] if earlier_gaps else ordered
    minute_bars = [bar for day in selected for bar in completed[day]]
    minute_days = [day for day in selected for _ in completed[day]]
    source = {'providerSymbol': raw['providerSymbol'], 'dailyEra': era,
              'validatedDaysIncludingWarmup': len(selected), 'firstCompleteDay': selected[0].isoformat(),
              'discardedDays': failures}
    return minute_bars, minute_days, raw['sessions'], daily, spec, source


def select_sdk(data, symbol, window):
    minutes, trading_days, sessions, daily, spec, source = validated_sdk_inputs(data, symbol, window)
    return {**score(minutes, trading_days, sessions, 15, daily, spec, window), 'source': source}


def total(instruments):
    result = {}
    for label in next(iter(instruments.values()))['results']:
        result[label] = {}
        for cost in ('1', '2'):
            runs = [value['results'][label][cost] for value in instruments.values()]
            rows = [run['metrics'] for run in runs]
            metrics = {key: sum(row[key] for row in rows)
                       for key in ('initialCash', 'netPnl', 'primaryOpens', 'addOpens', 'closedTrades',
                                   'longNetPnl', 'shortNetPnl', 'addNetPnl', 'fees', 'slippageCost')}
            curves = [run['dailyEquity'] for run in runs]
            dates = list(curves[0])
            if any(list(curve) != dates for curve in curves):
                raise ValueError('Cannot combine mismatched trade-day equity marks')
            peak = metrics['initialCash']
            drawdown = 0.0
            for day in dates:
                equity = sum(curve[day] for curve in curves)
                peak = max(peak, equity)
                drawdown = max(drawdown, (peak - equity) / peak)
            result[label][cost] = {**metrics, 'returnPct': metrics['netPnl'] / metrics['initialCash'] * 100,
                                   'dailyCloseMaxDrawdownPct': drawdown * 100}
    return result


def verify_sdk_glass(source):
    path = HISTORY / 'intraday-replay/FG701.json'
    archive = json.loads(path.read_bytes())
    tape = {sdk_stamp(row): row for row in source['contracts']['FG701']['minutes']}
    start, end = (day.isoformat() for day in ORIGINAL_WINDOW)
    rows = [row for row in aggregate_archived_minutes(archive['bars'], 900) if start <= row['tradingDate'] <= end]
    for row in rows:
        actual = tape[datetime.fromisoformat(row['timestamp'])]
        if any(actual[key] != row[key] for key in ('open', 'high', 'low', 'close', 'volume')):
            raise ValueError('Native FG 15m data differs from the independent archived 1m aggregation')
    if not rows:
        raise ValueError('No independently verifiable FG minute overlap')
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Choose a fresh output path')
    data = {'status': 'HISTORICAL_EXPLORATION', 'excluded': ['SC'], 'verifiedFGMinute1': audited_glass(ORIGINAL_WINDOW)}
    if args.sdk:
        payload = args.sdk.read_bytes()
        source = json.loads(payload)
        instruments = {symbol: select_sdk(source, symbol, MULTI_WINDOW) for symbol in CONTRACTS}
        data['matchedNative15'] = {'contracts': instruments, 'total': total(instruments),
                                   'nativeFG15MatchesFrom1m': verify_sdk_glass(source),
                                   'sourceSha256': sha256(payload).hexdigest(), 'source': source['source']}
    files = ('scripts/research_personal_ma_multiframe.py', 'backtesting/personal_ma_multiframe_execution.py',
             'backtesting/personal_ma_multiframe_signals.py', 'backtesting/personal_ma_signals.py',
             'backtesting/personal_ma_overlay.py', 'backtesting/chanlun_research.py',
             'scripts/theory_matrix_intraday.py', 'scripts/collect_personal_ma_minutes.py',
             'scripts/fg701_daily_macd.py', 'backtesting/backtester.py')
    data['codeSha256'] = {file: sha256((ROOT / file).read_bytes()).hexdigest() for file in files}
    with args.output.open('x', encoding='utf-8') as result:
        json.dump(data, result, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
        result.write('\n')
    print(args.output)


if __name__ == '__main__':
    main()
