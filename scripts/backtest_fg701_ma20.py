"""FG701 one-minute MA20, fixed stop, no take-profit, immediate reversal."""
from __future__ import annotations

import argparse
from collections import defaultdict, deque
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.backtest_fg701_intraday import SH, prepare, summarize, write_csv
from scripts.backtest_fg701_reversal import simulate_reversal, verify


def add_ma20(bars, warmup=(), period=20):
    if period < 1:
        raise ValueError('Invalid MA period')
    history = deque(warmup[-(period-1):] if period > 1 else [], maxlen=period)
    if any(not math.isfinite(c) or c <= 0 for c in history):
        raise ValueError('Invalid warmup close')
    result = []
    for b in bars:
        if not math.isfinite(b['close']) or b['close'] <= 0:
            raise ValueError('Invalid close')
        history.append(b['close'])
        result.append({**b, 'mean': math.fsum(history)/period if len(history) == period else None})
    return result


def prepare_ma20(raw):
    bars, audit = prepare(raw)
    if audit['status'] != 'PASS':
        raise ValueError('Source completeness check failed')
    first_ns = int(bars[0]['timestamp'].timestamp()*1e9)
    source_index = next(i for i,b in enumerate(raw['minute']) if int(b['datetime']) == first_ns)
    previous = raw['minute'][max(0, source_index-19):source_index]
    if len(previous) != 19:
        raise ValueError('MA20 requires 19 actual pre-window minute bars')
    dependencies = previous+[raw['minute'][source_index]]
    if any(b['id'] != a['id']+1 or b['datetime'] <= a['datetime'] for a,b in zip(dependencies, dependencies[1:])):
        raise ValueError('Noncontiguous MA20 warmup source IDs/timestamps')
    warmup = [b['close'] for b in previous]
    enriched = add_ma20(bars, warmup)
    # Independent reference: a literal window of the original closes, no deque state.
    closes = warmup+[b['close'] for b in bars]
    for i,b in enumerate(enriched):
        assert b['mean'] == math.fsum(closes[i:i+20])/20
    meta = {'indicator':'SMA20', 'barSeconds':60, 'periodBars':20, 'dailyReset':False,
            'volumeWeighted':False, 'warmupBars':19,
            'warmupFirstTimestamp':datetime.fromtimestamp(previous[0]['datetime']/1e9,SH).isoformat(),
            'warmupLastTimestamp':datetime.fromtimestamp(previous[-1]['datetime']/1e9,SH).isoformat(),
            'warmupSourceIds':[int(previous[0]['id']),int(previous[-1]['id'])],
            'firstSampleMean':enriched[0]['mean'], 'independentWindowChecks':len(enriched)}
    return enriched, audit, meta


def verify_ma_signals(trades, curve, bars, events):
    index = {b['timestamp'].isoformat():i for i,b in enumerate(bars)}
    for t in trades:
        if t['entryReason'] == 'INITIAL_SIDE':
            signal = bars[index[t['signalTime']]]
            assert t['side']*(signal['close']-signal['mean']) > 0
            assert t['entryTime'] > t['signalTime']
        if t['entryReason'] == 'REVERSE_MEAN_REVERSAL':
            signal = bars[index[t['signalTime']]]
            assert t['side']*(signal['close']-signal['mean']) >= 3-1e-9
            assert t['entryTime'] > t['signalTime']
        assert t['exitReason'] != 'TAKE_PROFIT'
        assert 'targetPrice' not in t
        assert all(c['mean'] == b['mean'] for c,b in zip(curve,bars))
    for day in {b['tradingDay'] for b in bars}:
        final = next(c for c in reversed(curve) if c['tradingDay'] == day)
        assert final['position'] == 0
    return {'status':'PASS','signalMA20Checks':len(trades),'noTakeProfit':True,'eachTradingDayFlat':True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT/'output/fg701-ma20-2026-11-17')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if (args.out/'results.json').exists():
        raise SystemExit('Preserving frozen study; use a new --out')
    raw_path = ROOT/'data/history/fg701-intraday-2026-11-17/raw.json'
    raw = json.loads(raw_path.read_text(encoding='utf-8'))
    assert raw['spec']['price_tick'] == 1 and raw['spec']['volume_multiple'] == 20
    bars, audit, indicator = prepare_ma20(raw)
    prior = json.loads((ROOT/'output/fg701-reversal-2026-11-17/results.json').read_text(encoding='utf-8'))
    result = {'status':'COMPLETE','strategy':'MINUTE_MA20_NO_TARGET_IMMEDIATE_REVERSAL','symbol':raw['symbol'],
              'window':prior['window'],'dataSha256':hashlib.sha256(raw_path.read_bytes()).hexdigest(),
              'sourceHashes':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
                             [Path(__file__),ROOT/'scripts/backtest_fg701_intraday.py',ROOT/'scripts/backtest_fg701_reversal.py',ROOT/'docs/plans/2026-11-17-fg701-minute-ma20.md']},
              'audit':audit,'indicator':indicator,'priorNoTargetVWAPBaseline':prior['scenarios']['high_first-baseline'],
              'scenarios':{},'assumptions':['MA20 is arithmetic mean of 20 completed one-minute closes, continuous across sessions/trading days.',
                                          'Use 19 observed pre-window candles; no daily indicator reset or future data.',
                                          'One lot, 10-tick fixed stop, no take-profit; reverse on stop and 3-tick opposite close across MA20.',
                                          'Close-confirmed entry/mean exit fills at next observed open; reversal at same reference with separate costs.',
                                          'No new entries after 14:58; 14:59 open liquidation; position state resets every trading day.',
                                          'Independent fixed intraminute O-H-L-C and O-L-H-C scenarios; not precise tick reconstruction.',
                                          'Assumed RMB 6 per lot per side; baseline adverse slippage 1 tick/side, stress 2 ticks/side.']}
    for path in ('HIGH_FIRST','LOW_FIRST'):
        for name,fee,slip in [('zero_cost',0,0),('baseline',6,1),('stress',6,2)]:
            key=path.lower()+'-'+name
            trades,curve,events=simulate_reversal(bars,fee=fee,slippage=slip,path=path)
            stats={'path':path,'feePerSide':fee,'slippageTicksPerSide':slip,**summarize(trades,curve)}
            stats['verification']=verify(trades,curve,events,stats)
            stats['ma20Verification']=verify_ma_signals(trades,curve,bars,events)
            daily=defaultdict(lambda:{'trades':0,'grossPnl':0,'fees':0,'slippageCost':0,'netPnl':0})
            for b in bars:
                _=daily[b['tradingDay']]
            for t in trades:
                daily[t['tradingDay']]['trades']+=1
                for k in ('grossPnl','fees','slippageCost','netPnl'):
                    daily[t['tradingDay']][k]+=t[k]
            assert sum(d['netPnl'] for d in daily.values())==stats['netPnl']
            for suffix,rows in [('trades',trades),('curve',curve),('events',events),('daily',[{'tradingDay':k,**v} for k,v in sorted(daily.items())])]:
                write_csv(args.out/f'{key}-{suffix}.csv',rows)
            result['scenarios'][key]=stats
    (args.out/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({'indicator':indicator,'scenarios':{k:{q:s[q] for q in ('trades','netPnl','winRate','maxMinuteCloseMarkedDrawdown','exitReasons')} for k,s in result['scenarios'].items()}},ensure_ascii=True))


if __name__ == '__main__':
    main()
