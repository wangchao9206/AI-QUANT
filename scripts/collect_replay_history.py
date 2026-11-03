"""Collect executable paper-replay archives, without replacing longer archives.

Run inside algorithm-service, whose environment already contains data credentials:
  python scripts/collect_replay_history.py --all
Each symbol runs in an isolated process with a deadline. Only validated actual
delivery OHLC, contract specifications and both roll legs enter the catalog.
"""
import argparse
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from data.history_manager import CORE_FUTURES_SYMBOLS
from data.tqsdk_backtest import (
    IncompleteDeliveryData, IncompleteRollData, TqSdkBacktestDataProvider, TqSdkBacktestUnavailable,
)


def collect_symbol(symbol, bars, refresh=False):
    provider = TqSdkBacktestDataProvider()
    cached = provider.cached_replay(symbol)
    target = provider._cache_path(symbol)
    # A valid archive can still be only a recent window. Check the original
    # request size, rather than treating any existing file as full history.
    if not refresh and cached is not None:
        existing = provider._read_cache(target, bars)
        if existing is not None and existing.complete:
            return archive_result(symbol, 'EXISTING', cached)
    meta = CORE_FUTURES_SYMBOLS[symbol]
    root = symbol[:-1]
    provider_root = root if meta['exchange'] in {'CZCE', 'CFFEX'} else root.lower()
    # Validate in isolation before publishing. Failure or timeout must leave
    # the currently usable archive untouched, including any longer history.
    with tempfile.TemporaryDirectory(prefix='.collect-', dir=provider.cache_dir) as staging:
        collector = TqSdkBacktestDataProvider(cache_dir=Path(staging))
        provider_symbol = f"KQ.m@{meta['exchange']}.{provider_root}"
        start_date = None
        gaps = []
        missing_days = []
        try:
            collector.load(symbol, provider_symbol, n=bars, force_download=True)
        except (IncompleteRollData, IncompleteDeliveryData) as exc:
            if not exc.missing_dates:
                raise
            # All earlier evidence remains unavailable for a continuous replay
            # through these gaps. Retry the longest verifiable recent suffix,
            # keeping its explicit date window separate from full history.
            if isinstance(exc, IncompleteDeliveryData):
                missing_days = [day.isoformat() for day in exc.missing_dates]
                gaps = [day.isoformat() for day in exc.missing_roll_dates]
                start_date = max([max(exc.missing_dates) + timedelta(days=1), *exc.missing_roll_dates])
            else:
                gaps = [day.isoformat() for day in exc.missing_dates]
                start_date = max(exc.missing_dates)
            collector.load(symbol, provider_symbol, n=bars, force_download=True, start_date=start_date)
        checked = collector.cached_replay(symbol)
        if checked is None:
            raise ValueError('archive validation failed')
        gap_details = {}
        if gaps:
            gap_details['missingRollDates'] = gaps
        if missing_days:
            gap_details['missingDeliveryDates'] = missing_days
        if cached is not None and (
            checked.bars[0].timestamp > cached.bars[0].timestamp
            or checked.bars[-1].timestamp < cached.bars[-1].timestamp
            or not {b.timestamp for b in cached.bars}.issubset({b.timestamp for b in checked.bars})
        ):
            return {**archive_result(symbol, 'PRESERVED', cached), **gap_details,
                    'reason': 'download_would_shorten_history',
                    'candidateStartDate': checked.bars[0].timestamp.date().isoformat()}
        os.replace(collector._cache_path(symbol, start_date), provider._cache_path(symbol, start_date))
        result = archive_result(symbol, 'READY_WITH_GAPS' if gaps or missing_days else 'READY', checked)
        result.update(gap_details)
        return result


def archive_result(symbol, status, dataset):
    return {'symbol': symbol, 'status': status, 'bars': len(dataset.bars),
            'rolls': len(dataset.roll_events), 'startDate': dataset.bars[0].timestamp.date().isoformat(),
            'endDate': dataset.bars[-1].timestamp.date().isoformat()}


def progress_result(result):
    """Keep console progress small; the status file retains every gap date."""
    compact = dict(result)
    for field in ('missingRollDates', 'missingDeliveryDates'):
        dates = compact.pop(field, [])
        if dates:
            compact[field + 'Count'] = len(dates)
            compact[field + 'Range'] = [dates[0], dates[-1]]
    return compact


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--all', action='store_true')
    parser.add_argument('--symbols', default='')
    parser.add_argument('--bars', type=int, default=10000,
                        help='daily history depth (default: SDK maximum, 10000; requests all available daily bars)')
    parser.add_argument('--timeout', type=int, default=900)
    parser.add_argument('--refresh', action='store_true', help='refresh even a current archive of the requested depth')
    parser.add_argument('--jobs', type=int, default=1, help='number of isolated download processes (1..4)')
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not 25 <= args.bars <= 10000 or args.timeout < 30:
        parser.error('bars must be 25..10000 and timeout must be at least 30 seconds')
    if not 1 <= args.jobs <= 4:
        parser.error('jobs must be 1..4')
    symbols = list(CORE_FUTURES_SYMBOLS) if args.all else [s.strip().upper() for s in args.symbols.split(',') if s.strip()]
    if not symbols or any(s not in CORE_FUTURES_SYMBOLS for s in symbols):
        parser.error('choose --all or known --symbols, e.g. AG0,AP0,SC0')
    if args.worker:
        symbol = symbols[0]
        # SDK startup messages can include identifiers. Emit only an allowlist.
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            try:
                result = collect_symbol(symbol, args.bars, args.refresh)
            except Exception as exc:
                result = {'symbol': symbol, 'status': 'UNAVAILABLE', 'reason': type(exc).__name__}
                if isinstance(exc, TqSdkBacktestUnavailable):
                    result['detail'] = str(exc)
        print(json.dumps(result), flush=True)
        return
    def run_symbol(symbol):
        started = time.monotonic()
        try:
            child = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--worker',
                                    '--symbols', symbol, '--bars', str(args.bars),
                                    *(['--refresh'] if args.refresh else [])],
                                   capture_output=True, text=True, timeout=args.timeout)
            result = json.loads(child.stdout.strip().splitlines()[-1]) if child.returncode == 0 else {'symbol': symbol, 'status': 'FAILED'}
        except subprocess.TimeoutExpired:
            result = {'symbol': symbol, 'status': 'TIMEOUT'}
        except (ValueError, IndexError):
            result = {'symbol': symbol, 'status': 'FAILED'}
        result['seconds'] = round(time.monotonic() - started, 1)
        result['requestedBars'] = args.bars
        return result

    results = []
    output = TqSdkBacktestDataProvider().cache_dir / f'collection-status-{symbols[0]}.json'
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        pending = [pool.submit(run_symbol, symbol) for symbol in dict.fromkeys(symbols)]
        for completed in as_completed(pending):
            result = completed.result()
            results.append(result)
            output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps(progress_result(result)), flush=True)
    print(json.dumps({'total': len(results), 'ready': sum(r['status'] in {'READY', 'EXISTING', 'READY_WITH_GAPS'} for r in results),
                      'withGaps': sum(r['status'] == 'READY_WITH_GAPS' for r in results)}), flush=True)


if __name__ == '__main__':
    main()
