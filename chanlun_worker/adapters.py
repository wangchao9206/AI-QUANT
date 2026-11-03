"""Only fixed, reviewed profiles are accepted; no user code/config forwarding."""
import importlib.metadata
import importlib.util
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
CHAN_COMMIT = 'f8ca3b5e44d7166e2abd756a8e7fa816c79faebe'
ADAPTER_VERSION = 'chan-observation-v1'


class NativeAdapter:
    engine_id = 'native'
    layers = ['FRACTAL', 'BI', 'SEGMENT', 'ZONE', 'BSP']

    def __init__(self):
        from .native import NativeEngine, PARAMETERS, VERSION
        self.analyzer = NativeEngine()
        self.parameters = dict(PARAMETERS)
        self.version = VERSION

    def push(self, bar):
        self.analyzer.push(bar)

    def structures(self):
        return self.analyzer.structures()


def line(kind, start, end, a, b, sure, **extra):
    return {'type': kind, 'startIndex': start, 'endIndex': end,
            'startPrice': float(a), 'endPrice': float(b),
            'direction': 'UP' if b >= a else 'DOWN', 'engineConfirmed': bool(sure), **extra}


class ChanPyAdapter:
    engine_id = 'chanpy'
    version = CHAN_COMMIT
    layers = ['BI', 'SEGMENT', 'ZONE']
    parameters = {'trigger_step': True, 'CTime.auto': False, 'profile': 'reviewed-defaults-v1'}

    def __init__(self):
        vendor = ROOT / 'third_party/chanpy'
        sys.path.insert(0, str(vendor)) if str(vendor) not in sys.path else None
        from ChanConfig import CChanConfig
        from Common.CEnum import KL_TYPE
        from KLine.KLine_List import CKLine_List
        self.analyzer = CKLine_List(KL_TYPE.K_DAY, CChanConfig({'trigger_step': True}))

    def push(self, bar):
        from Common.CEnum import KL_TYPE
        from Common.CTime import CTime
        from KLine.KLine_Unit import CKLine_Unit
        dt = datetime.fromisoformat(bar['timestamp'])
        unit = CKLine_Unit({'time_key': CTime(dt.year, dt.month, dt.day, 0, 0, auto=False),
                           **{key: bar[key] for key in ('open', 'high', 'low', 'close', 'volume')}})
        unit.set_idx(bar['index'])
        unit.kl_type = KL_TYPE.K_DAY
        self.analyzer.add_single_klu(unit)

    def structures(self):
        output = []
        for kind, items in [('BI', self.analyzer.bi_list), ('SEGMENT', self.analyzer.seg_list)]:
            output.extend(line(kind, b.get_begin_klu().idx, b.get_end_klu().idx,
                               b.get_begin_val(), b.get_end_val(), b.is_sure,
                               rawFlag='is_sure') for b in items)
        for z in self.analyzer.zs_list:
            if z.high >= z.low:
                output.append({'type': 'ZONE', 'startIndex': z.begin.idx, 'endIndex': z.end.idx,
                               'low': float(z.low), 'high': float(z.high), 'direction': 'RANGE',
                               'engineConfirmed': bool(z.is_sure), 'rawFlag': 'is_sure'})
        return output


class CzscAdapter:
    engine_id = 'czsc'
    version = '1.0.2'
    layers = ['BI', 'ZONE']
    parameters = {'max_bi_num': 10000, 'min_bi_len': 6, 'amount': 'UNAVAILABLE_PRICE_STRUCTURE_ONLY'}

    def __init__(self):
        if importlib.metadata.version('czsc') != self.version:
            raise ValueError('Unexpected CZSC version')
        self.analyzer = None
        self.indices = {}

    def push(self, bar):
        from czsc import CZSC, Freq, RawBar
        dt = datetime.fromisoformat(bar['timestamp']).replace(tzinfo=None)
        self.indices[dt] = bar['index']
        raw = RawBar(symbol='FU0', id=bar['index'], freq=Freq.D, dt=dt,
                     **{key: bar[key] for key in ('open', 'high', 'low', 'close')},
                     vol=bar['volume'], amount=0)
        if self.analyzer is None:
            self.analyzer = CZSC([raw], max_bi_num=10000, min_bi_len=6)
        else:
            self.analyzer.update(raw)

    def structures(self):
        a = self.analyzer
        sure = {(b.fx_a.dt, b.fx_b.dt) for b in a.finished_bis}
        output = [line('BI', self.indices[b.fx_a.dt], self.indices[b.fx_b.dt], b.fx_a.fx, b.fx_b.fx,
                       (b.fx_a.dt, b.fx_b.dt) in sure, rawFlag='finished_bis') for b in a.bi_list]
        output.extend({'type': 'ZONE', 'startIndex': self.indices[z.sdt], 'endIndex': self.indices[z.edt],
                       'low': float(z.zd), 'high': float(z.zg), 'direction': 'RANGE',
                       'engineConfirmed': None, 'rawFlag': 'zs_list_from_finished_bis'}
                      for z in a.zs_list if z.zg >= z.zd)
        return output


class BaselineAdapter:
    engine_id = 'baseline'
    version = 'fu-chanlun-causal-v1'
    layers = ['BI', 'SEGMENT', 'ZONE']
    parameters = {'family': 'CHAN_SEGMENT_T3', 'scale': 1.0}

    def __init__(self):
        # Load the existing, unchanged structural implementation without importing
        # the trading package facade (and its unrelated execution dependencies).
        name = '_aiquant_chanlun_baseline'
        if name not in sys.modules:
            spec = importlib.util.spec_from_file_location(name, ROOT / 'backtesting/chanlun_research.py')
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
        self.module = sys.modules[name]
        self.bars = []

    def push(self, bar):
        self.bars.append(SimpleNamespace(**bar))

    def structures(self):
        result = self.module.detect(self.bars, 'CHAN_SEGMENT_T3')
        output = []
        for kind, key in [('BI', 'pens'), ('SEGMENT', 'segments')]:
            output.extend(line(kind, b['startIndex'], b['endIndex'], b['startPrice'], b['endPrice'],
                               True, rawFlag='confirmedIndex', baselineConfirmedIndex=b['confirmedIndex'])
                          for b in result[key])
        output.extend({'type': 'ZONE', 'startIndex': z['startIndex'], 'endIndex': z['lastUnitEndIndex'],
                       'low': z['lower'], 'high': z['upper'], 'direction': 'RANGE',
                       'engineConfirmed': True, 'rawFlag': 'confirmedIndex',
                       'baselineConfirmedIndex': z['confirmedIndex']} for z in result['zones'])
        return output


ADAPTERS = {'native': NativeAdapter, 'chanpy': ChanPyAdapter, 'czsc': CzscAdapter, 'baseline': BaselineAdapter}
