"""Frozen native Chan candidates -> existing delivery-contract cash ledger.

No provider I/O, parameter search, orders, or filtering on final candidate state.
"""
from dataclasses import asdict
from datetime import date, datetime
import gzip
import hashlib
import json
from pathlib import Path

from backtesting.chanlun_research import detect, execute
from backtesting.independent_research import ResearchRisk, causal_prices
from chanlun_worker.analysis import analyze, canonical
from chanlun_worker.data import DATASET_HASH, DATASET_ID, ROOT, load_dataset
from data.data_feed import KLineBar
from data.tqsdk_backtest import FuturesContractSpec, RollEvent, TqSdkBacktestDataset

VERSION = 'native-chan-cost-lab-v1'
GROUPS = {'THIRD': ('B3', 'S3'), 'ALL': ('B1', 'S1', 'B2', 'S2', 'B3', 'S3')}


def execution_dataset():
    path = ROOT / 'docs/research/data/fu-chanlun-2026-10-30/source-snapshot.json.gz'
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != DATASET_HASH:
        raise ValueError('Execution snapshot checksum mismatch')
    d = json.loads(gzip.decompress(raw))
    bars = [KLineBar(**{**b, 'timestamp': datetime.fromisoformat(b['timestamp'])}) for b in d['bars']]
    rolls = [RollEvent(**{**r, 'execution_date': date.fromisoformat(r['execution_date'])}) for r in d['roll_events']]
    return TqSdkBacktestDataset(d['symbol'], d['provider_symbol'], d['source'],
        datetime.fromisoformat(d['generated_at']), bars, rolls,
        {k: FuturesContractSpec(**v) for k, v in d['contract_specs'].items()}, d['complete'])


def candidate_tape(analysis, group):
    """Read the FIRST observation, even if later revised, invalidated or retracted."""
    if group not in GROUPS:
        raise ValueError('Unknown frozen candidate group')
    dates = {b['date']: i for i, b in enumerate(analysis['bars'])}
    seen, tape, invalidations = set(), [], {}
    for record in analysis['events']:
        if record['type'] != 'BSP':
            continue
        index = dates[record['observedDate']]
        key = record['id']
        if record.get('signalState') == 'INVALIDATED' or record['eventType'] == 'RETRACTED':
            invalidations.setdefault(key, index)
        if key in seen or record['eventType'] != 'OBSERVED':
            continue
        seen.add(key)
        if record.get('signalType') not in GROUPS[group] or record.get('signalState') != 'CANDIDATE':
            continue
        if record['candidateObservedIndex'] != index or not 0 <= record['endIndex'] <= index:
            raise ValueError('Non-causal candidate observation')
        tape.append({'direction': 1 if record['direction'] == 'UP' else -1,
            'pivotIndex': record['endIndex'], 'confirmedIndex': index,
            'invalidation': record['invalidation'], 'source': record['signalType'],
            'structureId': key, 'observationEventSeq': record['eventSeq'],
            'evidence': record.get('evidence', {})})
    # Reject every colliding event: a declared neutral policy, not best-afterwards selection.
    counts = {}
    for e in tape:
        counts[e['confirmedIndex']] = counts.get(e['confirmedIndex'], 0) + 1
    accepted = [e for e in tape if counts[e['confirmedIndex']] == 1]
    conflicts = [dict(e, outcome='SIMULTANEOUS_CANDIDATES_SKIPPED') for e in tape if counts[e['confirmedIndex']] > 1]
    return tape, accepted, conflicts, invalidations


def run_lab(group='THIRD', initial_cash=1_000_000):
    if group not in GROUPS or initial_cash not in (100_000, 500_000, 1_000_000):
        raise ValueError('Unknown frozen research configuration')
    dataset = execution_dataset()
    signals = causal_prices(dataset)
    normalized = load_dataset()
    if len(signals) != len(normalized) or any(
            abs(getattr(a, k) - b[k]) > 1e-8
            for a, b in zip(signals, normalized) for k in ('open', 'high', 'low', 'close')):
        raise ValueError('Signal normalization differs from observation engine')
    analysis = analyze('native', len(signals))
    tape, accepted, conflicts, invalidations = candidate_tape(analysis, group)
    for event in tape:
        event['firstObservationDate'] = normalized[event['confirmedIndex']]['date']
        event['pivotDate'] = normalized[event['pivotIndex']]['date']
    risk = ResearchRisk()
    start, end = signals[80].timestamp.date(), signals[-1].timestamp.date()
    variants = []
    for name, cost, delay in [('NATIVE_BASE', 1, 0), ('NATIVE_DOUBLE_COST', 2, 0), ('NATIVE_DELAY_ONE', 1, 1)]:
        result = execute(dataset, accepted, initial_cash, start, end, cost_multiplier=cost,
                         delay=delay, signal_bars=signals, invalidation_observations=invalidations)
        decided = {e['structureId'] for e in result['decisions']}
        unexecuted = [dict(e, outcome='OUTSIDE_EXECUTION_WINDOW') for e in accepted if e['structureId'] not in decided]
        variants.append({'id': name, 'costMultiplier': cost, 'delayBars': delay, **result,
                         'excluded': conflicts + unexecuted})
    for family in ('RANGE_RETEST', 'CHANNEL_BREAKOUT'):
        events = detect(signals, family)['events']
        variants.append({'id': family, 'costMultiplier': 1, 'delayBars': 0,
                         **execute(dataset, events, initial_cash, start, end, signal_bars=signals), 'excluded': []})
    sources = [Path(__file__), ROOT/'backtesting/chanlun_research.py', ROOT/'backtesting/independent_research.py',
               ROOT/'backtesting/backtester.py', ROOT/'data/tqsdk_backtest.py']
    implementation = hashlib.sha256(b''.join(p.read_bytes().replace(b'\r\n', b'\n') for p in sources)).hexdigest()
    config = {'version': VERSION, 'datasetId': DATASET_ID, 'datasetHash': DATASET_HASH,
        'profileHash': analysis['profileHash'], 'implementationHash': implementation,
        'group': group, 'initialCash': initial_cash, 'risk': asdict(risk),
        'entry': 'FIRST_OBSERVATION_NEXT_DELIVERY_OPEN', 'collisionPolicy': 'SKIP_ALL',
        'invalidationExit': 'NEXT_OPEN_AFTER_OBSERVED_INVALIDATION', 'stopAtr': 2, 'targetAtr': 4,
        'maxHoldingBars': 20, 'warmupBars': 80, 'window': [str(start), str(end)]}
    return {'schemaVersion': 1, 'engineVersion': VERSION, 'config': config,
        'configHash': hashlib.sha256(canonical(config).encode()).hexdigest(),
        'candidateTape': tape, 'invalidationObservations': invalidations, 'variants': variants,
        'assumptions': [
            '冻结历史研究，规则已在这份历史上开发；不能称为未见样本或前向业绩。',
            '日线标签不等于精确可得时间；假设收盘后观察，下一交易日真实合约开盘执行。',
            '信号使用因果连续价，撮合使用交割合约原始价；换月日清仓并取消新单。',
            '合约规格为快照固定值，非逐日历史交易所费率和保证金；双倍成本只作敏感性检查。',
            '止损和止盈同日触发时先计止损；止损跳空按更差开盘，止盈按目标或越过目标的开盘价且滑点为零。',
            '原候选后续失效仍保留；收到失效观察后下一开盘退出，跳空可能超出预算。',
            '固定2ATR止损、4ATR止盈、最长20根；不代表完整缠论交易系统。',
            '普通突破/回踩采用相同风险与账本；信号数量不同，结果不证明因果收益优势。',
        ], 'executable': False}
