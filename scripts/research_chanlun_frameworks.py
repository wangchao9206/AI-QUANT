"""Offline structure-semantics probe; no orders, optimization or PnL backtest.

Run from a separate environment with czsc==1.0.2. Pass the reviewed chan.py
checkout explicitly. Input is the existing frozen FU archive, not live data.
"""
import argparse
import gzip
import hashlib
import importlib.metadata
import json
import math
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHAN_COMMIT = "f8ca3b5e44d7166e2abd756a8e7fa816c79faebe"


def prices(path):
    raw = path.read_bytes()
    data = json.loads(gzip.decompress(raw))
    assert data['complete'] and data['symbol'] == 'FU0'
    rolls = {row['execution_date']: row for row in data['roll_events']}
    assert len(rolls) == len(data['roll_events'])
    result, factor = [], 1.0
    for i, bar in enumerate(data['bars']):
        stamp = datetime.fromisoformat(bar['timestamp'])
        assert stamp.utcoffset().total_seconds() == 28800
        day = stamp.date().isoformat()
        event = rolls.get(day)
        if i and bar['contract_symbol'] != data['bars'][i-1]['contract_symbol']:
            previous = data['bars'][i-1]['contract_symbol']
            assert event and event['from_contract'] == previous and event['to_contract'] == bar['contract_symbol']
            assert event['old_open'] > 0 and event['new_open'] > 0
            factor *= event['old_open'] / event['new_open']
        elif i:
            assert not event
        record = {**bar, 'dt': stamp.replace(tzinfo=None)}
        for field in ('open', 'high', 'low', 'close'):
            assert math.isfinite(bar[field]) and bar[field] > 0
            record[field] = bar[field] * factor
        assert record['low'] <= min(record['open'], record['close']) <= max(record['open'], record['close']) <= record['high']
        if result:
            assert result[-1]['dt'] < record['dt']
        result.append(record)
    return result, {'path': str(path.relative_to(ROOT)).replace('\\', '/'), 'sha256': hashlib.sha256(raw).hexdigest(),
                    'bars': len(result), 'start': result[0]['dt'].date().isoformat(), 'end': result[-1]['dt'].date().isoformat(),
                    'rolls': len(rolls), 'normalization': 'forward ratio chain using observed old/new roll opens; timezone removed only after verifying UTC+8'}


class Observations:
    def __init__(self):
        self.previous = set()
        self.first_seen = {}
        self.removed = 0
        self.changed_steps = 0
        self.examples = []

    def add(self, index, values):
        current = set(values)
        removed = self.previous - current
        if removed:
            self.removed += len(removed)
            self.changed_steps += 1
            if len(self.examples) < 3:
                self.examples.append({'observedIndex': index, 'removed': sorted(removed)[:3]})
        for value in current:
            self.first_seen.setdefault(value, index)
        self.previous = current

    def result(self):
        lags = [seen-key[1] for key, seen in self.first_seen.items()]
        return {'finalCount': len(self.previous), 'distinctObservedTuples': len(self.first_seen),
                'tupleRemovals': self.removed, 'stepsWithTupleRemovals': self.changed_steps,
                'firstSeenMinusEndIndex': {'min': min(lags), 'median': statistics.median(lags), 'max': max(lags)} if lags else None,
                'examples': self.examples}


def probe_czsc(bars):
    from czsc import CZSC, Freq, RawBar
    keys = {bar['dt']: i for i, bar in enumerate(bars)}
    raw = [RawBar(symbol='FU0_RESEARCH', id=i, freq=Freq.D, dt=b['dt'], open=b['open'], high=b['high'],
                  low=b['low'], close=b['close'], vol=b['volume'], amount=0) for i, b in enumerate(bars)]
    def signature(items):
        return sorted((keys[b.fx_a.dt], keys[b.fx_b.dt], str(b.direction), round(b.high, 8), round(b.low, 8)) for b in items)
    analyzer = CZSC(raw[:1], max_bi_num=10000)
    all_bis, finished = Observations(), Observations()
    finished_removed_but_present = 0
    finished_removed_from_all = 0
    parity = []
    for i, bar in enumerate(raw):
        if i:
            analyzer.update(bar)
        all_keys = signature(analyzer.bi_list)
        finished_keys = signature(analyzer.finished_bis)
        removed = finished.previous - set(finished_keys)
        finished_removed_but_present += len(removed & set(all_keys))
        finished_removed_from_all += len(removed - set(all_keys))
        all_bis.add(i, all_keys)
        finished.add(i, finished_keys)
        if i in (100, 500, 1000, len(raw)-1):
            rebuilt = CZSC(raw[:i+1], max_bi_num=10000)
            parity.append({'prefixBars': i+1, 'allBisEqual': signature(rebuilt.bi_list) == signature(analyzer.bi_list),
                           'finishedBisEqual': signature(rebuilt.finished_bis) == signature(analyzer.finished_bis)})
    try:
        RawBar(symbol='TZ_PROBE', id=0, freq=Freq.D, dt=datetime(2026, 1, 1, tzinfo=timezone.utc),
               open=1, high=1, low=1, close=1, vol=1, amount=0)
        aware = 'accepted'
    except (ValueError, TypeError) as error:
        aware = f'{type(error).__name__}: {error}'
    return {'runtimeDistribution': {'czsc': importlib.metadata.version('czsc'), 'wbt': importlib.metadata.version('wbt')},
            'parameters': {'max_bi_num': 10000, 'min_bi_len': analyzer.min_bi_len},
            'bis': all_bis.result(), 'finishedBis': finished.result(), 'finalZones': len(analyzer.zs_list),
            'finishedBisRemovalClassification': {'stillInBiList': finished_removed_but_present, 'absentFromBiList': finished_removed_from_all},
            'prefixRebuildParity': parity, 'timezoneAwareInput': aware}


def probe_chanpy(bars, checkout):
    actual = subprocess.check_output(['git', '-C', str(checkout), 'rev-parse', 'HEAD'], text=True).strip()
    assert actual == CHAN_COMMIT, 'Unexpected chan.py source revision'
    sys.path.insert(0, str(checkout))
    from ChanConfig import CChanConfig
    from Common.CEnum import KL_TYPE
    from Common.CTime import CTime
    from KLine.KLine_List import CKLine_List
    from KLine.KLine_Unit import CKLine_Unit

    def new(step=True):
        return CKLine_List(KL_TYPE.K_DAY, CChanConfig({'trigger_step': step}))
    def push(analyzer, i):
        bar = bars[i]; dt = bar['dt']
        unit = CKLine_Unit({'time_key': CTime(dt.year, dt.month, dt.day, dt.hour, dt.minute, auto=False),
                           'open': bar['open'], 'high': bar['high'], 'low': bar['low'], 'close': bar['close'], 'volume': bar['volume']})
        unit.set_idx(i);unit.kl_type = KL_TYPE.K_DAY
        analyzer.add_single_klu(unit)
    def signature(items):
        return sorted((b.get_begin_klu().idx, b.get_end_klu().idx, str(b.dir),
                       round(max(b.get_begin_val(), b.get_end_val()), 8),
                       round(min(b.get_begin_val(), b.get_end_val()), 8)) for b in items)
    analyzer = new()
    all_bis, sure, signals = Observations(), Observations(), Observations()
    parity = []
    for i in range(len(bars)):
        push(analyzer, i)
        all_bis.add(i, signature(analyzer.bi_list))
        sure.add(i, signature(b for b in analyzer.bi_list if b.is_sure))
        signals.add(i, [(point.bi.get_begin_klu().idx, point.klu.idx, point.is_buy, kind.value)
                        for point in analyzer.bs_point_lst.bsp_iter() for kind in point.type])
        if i in (100, 500, 1000, len(bars)-1):
            rebuilt = new()
            for n in range(i+1):push(rebuilt, n)
            parity.append({'prefixBars': i+1, 'allBisEqual': signature(rebuilt.bi_list) == signature(analyzer.bi_list),
                           'sureBisEqual': signature(b for b in rebuilt.bi_list if b.is_sure) == signature(b for b in analyzer.bi_list if b.is_sure)})
    static = new(False)
    for i in range(len(bars)):push(static, i)
    static.cal_seg_and_zs()
    static_parity = {'allBisEqual': signature(static.bi_list) == signature(analyzer.bi_list),
                     'sureBisEqual': signature(b for b in static.bi_list if b.is_sure) == signature(b for b in analyzer.bi_list if b.is_sure),
                     'staticSegments': len(static.seg_list), 'incrementalSegments': len(analyzer.seg_list)}
    return {'sourceCommit': actual, 'parameters': {'trigger_step': True, 'otherSettings': 'CChanConfig defaults', 'CTime.auto': False},
            'bis': all_bis.result(), 'isSureBis': sure.result(), 'buySellPointAtoms': signals.result(),
            'finalSegments': len(analyzer.seg_list), 'finalZones': len(analyzer.zs_list), 'prefixRebuildParity': parity,
            'staticFinalizationVsIncremental': static_parity}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--chanpy', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source = ROOT / 'docs/research/data/fu-chanlun-2026-10-30/source-snapshot.json.gz'
    bars, evidence = prices(source)
    result = {'purpose': 'Structure state and observation-time semantics only; no profit, order or comparative-performance claim',
              'input': evidence, 'python': sys.version, 'czsc': probe_czsc(bars), 'chanpy': probe_chanpy(bars, args.chanpy.resolve())}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'bars': len(bars), 'czscBis': result['czsc']['bis']['finalCount'],
                      'chanpyBis': result['chanpy']['bis']['finalCount'], 'output': str(args.output)}, ensure_ascii=True))


if __name__ == '__main__':
    main()
