#!/usr/bin/env python3
"""Initialize or advance a local FU diagnostic account from audited completed bars.

This is an on-demand OHLC replay, not a background trader or actual market fill.
"""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtesting.fuel_observation import freeze,advance,atomic_save,state_lock
from data.tqsdk_backtest import TqSdkBacktestDataProvider
from data.trading_day import completed_daily_bar

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--input',required=True,help='Complete TqSdk schema-v2 FU archive, never a synthetic replacement')
    parser.add_argument('--state',default='docs/research/data/fu-regime-2026-10-27/shadow-state.json')
    parser.add_argument('--initialize',action='store_true')
    parser.add_argument('--candidate',default='docs/research/data/fu-regime-2026-10-27/observation-candidate.json')
    args=parser.parse_args();state_path=ROOT/args.state;input_path=ROOT/args.input
    data=TqSdkBacktestDataProvider(cache_dir=ROOT/'.test-tmp')._read_cache(input_path,0,allow_stale=True)
    if data is None or any(not completed_daily_bar(b.timestamp) for b in data.bars):raise ValueError('Only complete real dated observations accepted')
    state_path.parent.mkdir(parents=True,exist_ok=True)
    with state_lock(state_path):
        if args.initialize:
            if state_path.exists():raise ValueError('Existing journal cannot be reset')
            candidate=json.loads((ROOT/args.candidate).read_text(encoding='utf-8'))
            if candidate['asOf']!=str(data.bars[-1].timestamp.date()):raise ValueError('Candidate must be frozen at matching observed cutoff')
            state=freeze(data,candidate['definition'])
            state['researchOrigin']={'family':candidate['selected']['family'],'mode':candidate['selected']['mode'],
                                      'status':candidate['qualification']}
        else:
            if not state_path.exists():raise ValueError('Initialize an explicitly frozen candidate first')
            state=advance(json.loads(state_path.read_text(encoding='utf-8')),data)
        atomic_save(state_path,state)
    print(json.dumps({'status':state['status'],'revision':state['revision'],'asOf':state['asOf'],
        'virtualCash':state['cash'],'markedEquity':state['equity'],'position':state['position'],
        'nextSignal':state['nextSignal']['signal'],'actualOrdersSubmitted':0},ensure_ascii=True))
if __name__=='__main__':main()
