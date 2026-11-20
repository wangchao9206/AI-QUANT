"""Build aligned FG701 signals and replay them over observed one-minute bars."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from hashlib import sha256
import json
from pathlib import Path

from data.data_feed import KLineBar
from data.intraday_replay import SH, _read
from data.tqsdk_backtest import FuturesContractSpec
from scripts.backtest_fg701_intraday import prepare


PERIODS = (15, 30, 60)
WINDOWS = {
    'all': (date(2026, 10, 19), date(2026, 11, 16)),
    '2026-10-19--2026-10-30': (date(2026, 10, 19), date(2026, 10, 30)),
    '2026-11-02--2026-11-16': (date(2026, 11, 2), date(2026, 11, 16)),
}
MINUTE = timedelta(minutes=1)


def _ohlcv(row):
    return tuple(row[field] for field in ('open', 'high', 'low', 'close', 'volume'))


def _load(archive_path, raw_path):
    """Cross-check the replay archive against the immutable provider capture."""
    arc_stat = archive_path.stat()
    archive = _read(str(archive_path.resolve()), arc_stat.st_mtime_ns, arc_stat.st_size)
    if (archive['symbol'], archive.get('providerSymbol')) != ('FG701', 'CZCE.FG701'):
        raise ValueError('This minute matrix requires the verified CZCE.FG701 archive')
    start, end = WINDOWS['all']
    if (archive['startDate'], archive['endDate']) != (start.isoformat(), end.isoformat()):
        raise ValueError('Replay does not describe the frozen scoring dates')
    raw_payload = raw_path.read_bytes()
    raw_hash = sha256(raw_payload).hexdigest()
    if archive['sourceSha256'] != raw_hash:
        raise ValueError('Replay archive and raw capture checksums disagree')
    raw = json.loads(raw_payload)
    scored, audit = prepare(raw, start, end)
    if audit['status'] != 'PASS':
        raise ValueError(f'Provider session audit failed: {audit["errors"]}')

    minute_refs = raw['minute'][:-1] if raw.get('lastMinuteProvisional') else raw['minute']
    verified_by_time = {
        datetime.fromtimestamp(row['datetime'] / 1e9, SH): _ohlcv(row)
        for row in minute_refs
    }
    if len(verified_by_time) != len(minute_refs):
        raise ValueError('Duplicate minute in provider capture')
    expected = [(row['timestamp'], row['tradingDay'], _ohlcv(row)) for row in scored]
    scoring_rows, bars, trading_days = [], [], []
    for row in archive['bars']:
        stamp = datetime.fromisoformat(row['timestamp']).astimezone(SH)
        day = date.fromisoformat(row['tradingDate'])
        if row['contract'] != archive['symbol'] or stamp.second or stamp.microsecond:
            raise ValueError('Replay minute has unexpected contract or time precision')
        prices = _ohlcv(row)
        if verified_by_time.get(stamp) != prices:
            raise ValueError(f'Replay minute differs from provider capture at {stamp.isoformat()}')
        if start <= day <= end:
            scoring_rows.append((stamp, day.isoformat(), prices))
        if day <= end:
            bars.append(KLineBar(stamp, *prices[:4], int(prices[4]), row.get('openInterest', 0), row['contract']))
            trading_days.append(day)
    if scoring_rows != expected:
        raise ValueError('Replay minute tape does not cover the audited trading days exactly')

    session_definitions = raw['spec']['trading_time']
    sessions = tuple(
        (time.fromisoformat(first), time.fromisoformat(last))
        for first, last in session_definitions['day'] + session_definitions['night']
    )
    spec_row = archive['spec']
    if (spec_row['priceTick'], spec_row['volumeMultiple']) != (raw['spec']['price_tick'], raw['spec']['volume_multiple']):
        raise ValueError('Contract tick or lot size disagrees with the provider capture')
    spec = FuturesContractSpec(
        contract=spec_row['contract'], volume_multiple=int(spec_row['volumeMultiple']), price_tick=spec_row['priceTick'],
        margin_per_lot=spec_row['marginPerLot'], commission_per_lot=spec_row['commissionPerLot'],
    )
    source = {
        'symbol': archive['providerSymbol'], 'archiveFile': archive_path.name, 'rawFile': raw_path.name,
        'archiveSha256': sha256(archive_path.read_bytes()).hexdigest(), 'rawSha256': raw_hash,
        'firstMinute': bars[0].timestamp.isoformat(), 'lastMinute': bars[-1].timestamp.isoformat(),
        'minuteBarsWithWarmup': len(bars), 'scoringMinuteBars': len(scored), 'scoringDays': audit['days'],
        'dailyOHLCVChecks': audit['dailyReferenceChecks'], 'contractSpec': vars(spec),
        'sessions': [[first.isoformat(), last.isoformat()] for first, last in sessions],
    }
    return bars, trading_days, sessions, spec, source


def aggregate_complete(bars, trading_days, sessions, minutes):
    """Build full windows anchored at each observed session's scheduled opening."""
    if minutes not in PERIODS or len(bars) != len(trading_days):
        raise ValueError('Invalid minute aggregation inputs')
    size = timedelta(minutes=minutes)
    groups = defaultdict(list)
    for bar, trading_day in zip(bars, trading_days):
        clock = bar.timestamp.time()
        session = next(((first, last) for first, last in sessions if first <= clock < last), None)
        if session is None:
            raise ValueError(f'Minute outside FG701 sessions: {bar.timestamp.isoformat()}')
        first, last = session
        today = bar.timestamp.date()
        session_open = datetime.combine(today, first, SH)
        session_close = datetime.combine(today, last, SH)
        start = session_open + ((bar.timestamp - session_open) // size) * size
        if start + size <= session_close:
            groups[(start, trading_day)].append(bar)

    result, result_days = [], []
    for (start, day), rows in sorted(groups.items()):
        if len(rows) != minutes or any(row.timestamp != start + i * MINUTE for i, row in enumerate(rows)):
            continue
        first, last = rows[0], rows[-1]
        result.append(KLineBar(
            start + size, first.open, max(row.high for row in rows), min(row.low for row in rows),
            last.close, sum(row.volume for row in rows), last.open_interest, last.contract_symbol,
        ))
        result_days.append(day)
    return result, result_days


def run_intraday(archive_path: Path, raw_path: Path | None = None) -> dict:
    from backtesting.theory_matrix import dow_structure_up, variants
    from backtesting.theory_matrix_execution import run_minute_execution

    archive_path = Path(archive_path)
    if raw_path is None:
        raw_path = archive_path.parent.parent / 'fg701-intraday-2026-11-17' / 'raw.json'
    bars, days, sessions, spec, source = _load(archive_path, Path(raw_path))
    aggregates, coverage = {}, {}
    run_count = 0
    for minutes in PERIODS:
        signal_bars, signal_days = aggregate_complete(bars, days, sessions, minutes)
        if not signal_bars:
            raise ValueError(f'No complete {minutes}-minute signal bars')
        age = 120 // minutes
        candidates = variants(signal_bars, signal_bars, dow_structure_up(signal_bars), wyckoff_setup_bars=age)
        stops = range(30, len(signal_bars), max(20, len(signal_bars) // 5))
        for stop in stops:
            prefix = signal_bars[:stop]
            actual = variants(prefix, prefix, dow_structure_up(prefix), wyckoff_setup_bars=age)
            expected = {name: [event for event in events if event['confirmedIndex'] < stop]
                        for name, events in candidates.items()}
            if actual != expected:
                raise AssertionError(f'{minutes}-minute prefix changed previously published signals at {stop}')
        key = str(minutes)
        coverage[key] = {
            'warmupAndScoringBars': len(signal_bars), 'wyckoffSetupBars': age,
            'scoringBars': sum(WINDOWS['all'][0] <= day <= WINDOWS['all'][1] for day in signal_days),
            'firstAvailableAt': signal_bars[0].timestamp.isoformat(),
            'lastAvailableAt': signal_bars[-1].timestamp.isoformat(),
            'signalPrefixChecks': len(stops),
        }
        aggregates[key] = {name: {} for name in candidates}
        for label, (start, end) in WINDOWS.items():
            for name, events in candidates.items():
                eligible = [{**e, 'invalidation': 0.0} for e in events
                            if start <= signal_days[e['confirmedIndex']] <= end]
                for cost in (1, 2):
                    metric = run_minute_execution(bars, days, signal_bars, minutes * 60, eligible, start, end, spec, cost)
                    aggregates[key][name][f'{label}@{cost}x'] = {'candidates': len(eligible), **metric}
                    run_count += 1
    return {'source': source, 'coverage': coverage, 'aggregates': aggregates, 'runCount': run_count,
            'windows': {label: [start.isoformat(), end.isoformat()] for label, (start, end) in WINDOWS.items()},
            'dowProxy': 'SAME_CONTRACT_CONFIRMED_SWINGS',
            'aggregation': 'COMPLETE_SESSION_OPEN_ANCHORED_BARS',
            'structureExit': False,
            'executionClock': 'OBSERVED_ONE_MINUTE_OPENS_AND_BARS'}
