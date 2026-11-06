"""Version-pinned Chan candidates for historical next-open paper experiments."""
from copy import deepcopy
from datetime import timezone
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
from pathlib import Path

from chanlun_worker.native import NativeEngine, PARAMETERS, VERSION

QUALIFICATION = 'HISTORICAL_NEXT_OPEN_ONLY_V1'
EXIT_RULE = 'ANY_SAME_DIRECTION_INVALIDATED'
GROUPS = {'THIRD': {'B3', 'S3'}, 'ALL': {'B1', 'S1', 'B2', 'S2', 'B3', 'S3'}}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def profile():
    root = Path(__file__).resolve().parents[1]
    sources = ['chanlun_worker/native.py', 'backtesting/chan_signal.py', 'backtesting/workflow.py']
    implementation = digest({p: hashlib.sha256((root / p).read_bytes().replace(b'\r\n', b'\n')).hexdigest() for p in sources})
    return {'engineId': 'native', 'engineVersion': VERSION, 'implementationHash': implementation,
            'rulesHash': digest({'parameters': PARAMETERS, 'qualification': QUALIFICATION, 'exitRule': EXIT_RULE}),
            'inputBasis': 'OBSERVED_CONTINUOUS_DAILY', 'priceQuantization': 'DECIMAL_HALF_UP_6',
            'qualification': QUALIFICATION, 'exitRule': EXIT_RULE}


def validate_params(params):
    expected = profile()
    if set(params) != set(expected) | {'group'} or not isinstance(params.get('group'),str) or params.get('group') not in GROUPS:
        raise ValueError('缠论节点需要完整的服务器规则指纹及具名候选范围')
    if any(params.get(k) != value for k, value in expected.items()):
        raise ValueError('缠论源码或规则版本已变化；旧配置仅可查阅，请显式创建新版本')


def input_bar(bar, index):
    prices = {k: float(Decimal(str(getattr(bar, k))).quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP))
              for k in ('open', 'high', 'low', 'close')}
    return {'index': index, 'timestamp': bar.timestamp.astimezone(timezone.utc).isoformat(),
            **prices, 'volume': int(bar.volume), 'contract': bar.contract_symbol}


class ChanTape:
    """Copy each observation immediately, before the mutable kernel can revise it."""
    def __init__(self, bars):
        self.rows = []
        engine, seen, invalidated = NativeEngine(), set(), set()
        prefix = hashlib.sha256()
        for index, bar in enumerate(bars):
            source = input_bar(bar, index)
            prefix.update((canonical(source) + '\n').encode())
            engine.push(source)
            candidates, withdrawals = [], []
            for raw in engine.zones.signals:
                key = digest([raw['signalType'], raw['candidateObservedIndex'], raw['endIndex'], raw['direction'], raw['invalidation']])[:24]
                event = {**deepcopy(raw), 'structureId': key,
                         'firstObservedAt': bars[raw['candidateObservedIndex']].timestamp.astimezone(timezone.utc).isoformat(),
                         'observedAt': source['timestamp'], 'eligibleAt': None}
                if key not in seen:
                    seen.add(key)
                    if raw['candidateObservedIndex'] != index:
                        raise ValueError('缠论候选首次观察界限不一致')
                    if raw['signalState'] == 'CANDIDATE':
                        candidates.append(event)
                if raw.get('invalidatedIndex') == index and key not in invalidated:
                    invalidated.add(key)
                    withdrawals.append(event)
            self.rows.append({'candidates': candidates, 'invalidations': withdrawals,
                              'inputHash': prefix.hexdigest(), 'inputBars': index + 1,
                              'windowStart': bars[0].timestamp.astimezone(timezone.utc).isoformat(), 'observedAt': source['timestamp'],
                              'priceQuantization': 'DECIMAL_HALF_UP_6',
                              'priceBasis': 'OBSERVED_CONTINUOUS_DAILY', 'qualification': QUALIFICATION,
                              'exitRule': EXIT_RULE, 'referenceLessons': [20, 21, 24, 62]})

    def observation(self, index, params, direction):
        value = deepcopy(self.rows[index])
        for kind in ('candidates', 'invalidations'):
            value[kind] = [s for s in value[kind] if s['signalType'] in GROUPS[params['group']]]
        value['profile'] = dict(params)
        buy = any(s['direction'] == 'UP' for s in value['candidates'])
        sell = any(s['direction'] == 'DOWN' for s in value['candidates'])
        close = any((1 if s['direction'] == 'UP' else -1) == direction for s in value['invalidations']) if direction else False
        return {'buy': buy, 'sell': sell, 'close': close}, value
