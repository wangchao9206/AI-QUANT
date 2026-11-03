import argparse
import json
import sys
from pathlib import Path

parser = argparse.ArgumentParser(description='Export actual historical structures for the Chan module design preview.')
parser.add_argument('--chanpy', type=Path, required=True, help='Pinned chan.py checkout')
args = parser.parse_args()
root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(root / 'scripts'))
from research_chanlun_frameworks import prices
from czsc import CZSC, Freq, RawBar

sys.path.insert(0, str(args.chanpy.resolve()))
from ChanConfig import CChanConfig
from Common.CEnum import KL_TYPE
from Common.CTime import CTime
from KLine.KLine_List import CKLine_List
from KLine.KLine_Unit import CKLine_Unit

bars, evidence = prices(root / 'docs/research/data/fu-chanlun-2026-10-30/source-snapshot.json.gz')
indices = {bar['dt']: index for index, bar in enumerate(bars)}
czsc = CZSC([RawBar(symbol='FU0', id=0, freq=Freq.D, dt=bars[0]['dt'], **{k: bars[0][k] for k in ['open', 'high', 'low', 'close']}, vol=bars[0]['volume'], amount=0)], max_bi_num=10000)
chan = CKLine_List(KL_TYPE.K_DAY, CChanConfig({'trigger_step': True}))
snapshots = []
for index, bar in enumerate(bars):
    if index:
        czsc.update(RawBar(symbol='FU0', id=index, freq=Freq.D, dt=bar['dt'], **{k: bar[k] for k in ['open', 'high', 'low', 'close']}, vol=bar['volume'], amount=0))
    dt = bar['dt']
    unit = CKLine_Unit({'time_key': CTime(dt.year, dt.month, dt.day, dt.hour, dt.minute, auto=False), **{k: bar[k] for k in ['open', 'high', 'low', 'close']}, 'volume': bar['volume']})
    unit.set_idx(index); unit.kl_type = KL_TYPE.K_DAY
    chan.add_single_klu(unit)
    if index + 1 not in [1814, 1854, 1874, 1894]:
        continue
    start = index - 71
    def xy(start_index, end_index, start_price, end_price, sure):
        return {'start': start_index, 'end': end_index, 'a': round(start_price, 5), 'b': round(end_price, 5), 'sure': sure}
    cz_bis = [xy(indices[b.fx_a.dt], indices[b.fx_b.dt], b.fx_a.fx, b.fx_b.fx, any(f.fx_a.dt == b.fx_a.dt and f.fx_b.dt == b.fx_b.dt for f in czsc.finished_bis)) for b in czsc.bi_list]
    ch_bis = [xy(b.get_begin_klu().idx, b.get_end_klu().idx, b.get_begin_val(), b.get_end_val(), b.is_sure) for b in chan.bi_list]
    ch_segs = [xy(b.get_begin_klu().idx, b.get_end_klu().idx, b.get_begin_val(), b.get_end_val(), b.is_sure) for b in chan.seg_list]
    cz_zones = [{'start': indices[z.sdt], 'end': indices[z.edt], 'low': round(z.zd, 5), 'high': round(z.zg, 5)} for z in czsc.zs_list if z.zg >= z.zd]
    ch_zones = [{'start': z.begin.idx, 'end': z.end.idx, 'low': round(z.low, 5), 'high': round(z.high, 5)} for z in chan.zs_list if z.high >= z.low]
    snapshots.append({'observedBars': index + 1, 'date': dt.date().isoformat(), 'start': start,
                      'bars': [{'i': n, 'date': b['dt'].date().isoformat(), **{k: round(b[k], 5) for k in ['open', 'high', 'low', 'close']}} for n, b in enumerate(bars[start:index+1], start)],
                      'chanpy': {'bis': [b for b in ch_bis if b['end'] >= start], 'segments': [b for b in ch_segs if b['end'] >= start], 'zones': [z for z in ch_zones if z['end'] >= start], 'totalBis': len(ch_bis), 'totalSegments': len(ch_segs), 'totalZones': len(ch_zones)},
                      'czsc': {'bis': [b for b in cz_bis if b['end'] >= start], 'segments': [], 'zones': [z for z in cz_zones if z['end'] >= start], 'totalBis': len(cz_bis), 'totalSegments': None, 'totalZones': len(cz_zones)}})
destination = root / 'docs/plans/chanlun-center-design-2026-10-31'
destination.mkdir(parents=True, exist_ok=True)
(destination / 'prototype-snapshots.json').write_text(json.dumps({'purpose': 'Design preview using frozen historical data; not live market data or an operational replay service', 'input': evidence, 'snapshots': snapshots}, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
print('Exported', len(snapshots), 'real historical snapshots for design preview')
