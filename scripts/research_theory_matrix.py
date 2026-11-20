"""Reproduce the daily SMA and intraday timeframe theory matrices."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.theory_matrix_daily import run_daily
from scripts.theory_matrix_intraday import run_intraday


RESEARCH_FILES = (
    'scripts/research_theory_matrix.py',
    'scripts/theory_matrix_daily.py',
    'scripts/theory_matrix_intraday.py',
    'scripts/research_dow_wyckoff_chan.py',
    'scripts/backtest_fg701_intraday.py',
    'backtesting/theory_matrix.py',
    'backtesting/theory_matrix_execution.py',
    'backtesting/chanlun_research.py',
    'backtesting/independent_research.py',
    'backtesting/backtester.py',
    'data/intraday_replay.py',
    'data/tqsdk_backtest.py',
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--daily-input', type=Path, default=ROOT / 'data/history/tqsdk-roll')
    parser.add_argument('--minute-input', type=Path, default=ROOT / 'data/history/intraday-replay/FG701.json')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Choose a fresh output path to preserve the previous results')
    fingerprints = {path: sha256((ROOT / path).read_bytes()).hexdigest() for path in RESEARCH_FILES}
    result = {'status': 'HISTORICAL_EXPLORATION', 'sourceHashes': fingerprints,
              'daily': run_daily(args.daily_input), 'intraday': run_intraday(args.minute_input)}
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
        stream.write('\n')
    print(f'Theory matrices written to {args.output}')


if __name__ == '__main__':
    main()
