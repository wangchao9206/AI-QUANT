"""Collect executable paper-replay archives, without replacing longer archives.

Run inside algorithm-service, whose environment already contains data credentials:
  python scripts/collect_replay_history.py --all --bars 600
Each symbol runs in an isolated process with a deadline. Only validated actual
delivery OHLC, contract specifications and both roll legs enter the catalog.
"""
import argparse
import contextlib
import io
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from data.history_manager import CORE_FUTURES_SYMBOLS
from data.tqsdk_backtest import TqSdkBacktestDataProvider


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--all', action='store_true')
    parser.add_argument('--symbols', default='')
    parser.add_argument('--bars', type=int, default=600)
    parser.add_argument('--timeout', type=int, default=240)
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not 25 <= args.bars <= 8000 or args.timeout < 30:
        parser.error('bars must be 25..8000 and timeout must be at least 30 seconds')
    symbols = list(CORE_FUTURES_SYMBOLS) if args.all else [s.strip().upper() for s in args.symbols.split(',') if s.strip()]
    if not symbols or any(s not in CORE_FUTURES_SYMBOLS for s in symbols):
        parser.error('choose --all or known --symbols, e.g. AG0,AP0,SC0')
    if args.worker:
        symbol = symbols[0]
        # SDK startup messages can include identifiers. Emit only an allowlist.
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            provider = TqSdkBacktestDataProvider()
            cached = provider.cached_replay(symbol)
            if cached is not None:
                result = {'symbol': symbol, 'status': 'EXISTING', 'bars': len(cached.bars)}
            else:
                meta = CORE_FUTURES_SYMBOLS[symbol]
                root = symbol[:-1]
                provider_root = root if meta['exchange'] in {'CZCE', 'CFFEX'} else root.lower()
                try:
                    data = provider.load(symbol, f"KQ.m@{meta['exchange']}.{provider_root}", n=args.bars)
                    checked = provider.cached_replay(symbol)
                    if checked is None:
                        raise ValueError('archive validation failed')
                    result = {'symbol': symbol, 'status': 'READY', 'bars': len(data.bars),
                              'rolls': len(data.roll_events), 'startDate': data.bars[0].timestamp.date().isoformat(),
                              'endDate': data.bars[-1].timestamp.date().isoformat()}
                except Exception as exc:
                    result = {'symbol': symbol, 'status': 'UNAVAILABLE', 'reason': type(exc).__name__}
        print(json.dumps(result), flush=True)
        return
    results = []
    for symbol in dict.fromkeys(symbols):
        started = time.monotonic()
        try:
            child = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--worker',
                                    '--symbols', symbol, '--bars', str(args.bars)],
                                   capture_output=True, text=True, timeout=args.timeout)
            result = json.loads(child.stdout.strip().splitlines()[-1]) if child.returncode == 0 else {'symbol': symbol, 'status': 'FAILED'}
        except subprocess.TimeoutExpired:
            result = {'symbol': symbol, 'status': 'TIMEOUT'}
        except (ValueError, IndexError):
            result = {'symbol': symbol, 'status': 'FAILED'}
        result['seconds'] = round(time.monotonic() - started, 1)
        results.append(result)
        print(json.dumps(result), flush=True)
    output = TqSdkBacktestDataProvider().cache_dir / f'collection-status-{symbols[0]}.json'
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'total': len(results), 'ready': sum(r['status'] in {'READY', 'EXISTING'} for r in results)}), flush=True)


if __name__ == '__main__':
    main()
