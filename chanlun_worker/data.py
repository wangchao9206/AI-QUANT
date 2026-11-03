"""Pinned, read-only dataset. Dates here are labels, not execution timestamps."""
import gzip
import hashlib
import json
import math
from datetime import datetime
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATASET_ID = 'fu-daily-2026-10-30'
DATASET_HASH = 'f069d8c21ec41d106f4b21c90f9e04d4d285d00847c8f551ff11991e38768577'
PRICE_BASIS = 'forward-observed-roll-ratio-v1'


@lru_cache(maxsize=1)
def load_dataset():
    raw = (ROOT / 'docs/research/data/fu-chanlun-2026-10-30/source-snapshot.json.gz').read_bytes()
    if hashlib.sha256(raw).hexdigest() != DATASET_HASH:
        raise ValueError('Frozen dataset checksum mismatch')
    data = json.loads(gzip.decompress(raw))
    if not data['complete'] or data['symbol'] != 'FU0':
        raise ValueError('Incomplete or unexpected dataset')
    rolls = {r['execution_date']: r for r in data['roll_events']}
    if len(rolls) != len(data['roll_events']):
        raise ValueError('Duplicate roll evidence')
    bars, factor = [], 1.0
    for i, raw_bar in enumerate(data['bars']):
        stamp = datetime.fromisoformat(raw_bar['timestamp'])
        if stamp.utcoffset().total_seconds() != 28800:
            raise ValueError('Expected Asia/Shanghai input')
        day = stamp.date().isoformat()
        roll = rolls.get(day)
        if i and raw_bar['contract_symbol'] != data['bars'][i - 1]['contract_symbol']:
            if (not roll or roll['from_contract'] != data['bars'][i - 1]['contract_symbol']
                    or roll['to_contract'] != raw_bar['contract_symbol']
                    or min(roll['old_open'], roll['new_open']) <= 0):
                raise ValueError('Missing contract roll evidence')
            factor *= roll['old_open'] / roll['new_open']
        elif i and roll:
            raise ValueError('Unexpected roll evidence')
        bar = {'index': i, 'date': day, 'timestamp': raw_bar['timestamp'],
               'contract': raw_bar['contract_symbol'], 'volume': raw_bar['volume']}
        for key in ('open', 'high', 'low', 'close'):
            value = raw_bar[key] * factor
            if not math.isfinite(value) or value <= 0:
                raise ValueError('Invalid OHLC')
            bar[key] = value
        if not bar['low'] <= min(bar['open'], bar['close']) <= max(bar['open'], bar['close']) <= bar['high']:
            raise ValueError('Invalid candle range')
        if bars and bars[-1]['date'] >= day:
            raise ValueError('Unordered bars')
        bars.append(bar)
    return bars


def catalog():
    bars = load_dataset()
    return {'id': DATASET_ID, 'sha256': DATASET_HASH, 'symbol': 'FU0', 'displayName': '燃油',
            'frequency': 'DAY', 'mode': 'FROZEN_HISTORY', 'priceBasis': PRICE_BASIS,
            'bars': len(bars), 'start': bars[0]['date'], 'end': bars[-1]['date'],
            'timeSemantics': 'TRADING_DATE_LABEL_ONLY', 'executable': False}
