"""Frozen descriptive daily study; no production orders or parameter searches."""
import csv,hashlib,json,math,statistics,sys
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backtesting.independent_research import causal_prices
from backtesting.trend_features import CONDITIONS,features
from data.tqsdk_backtest import TqSdkBacktestDataProvider

OUT=ROOT/'docs/research/data/trend-opportunities-2026-11-07'
HORIZONS=(1,3,5,10)
def dump(path,data):path.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def stage(day):return 'DEVELOPMENT' if day<'2023-01-01' else 'VALIDATION' if day<'2025-01-01' else 'RETROSPECTIVE_2025_2026'
def summarize(rows):
    values=[r['netPct'] for r in rows];loss=sum(-v for v in values if v<0)
    return {'samples':len(rows),'symbols':len({r['symbol'] for r in rows}),
        'winPct':sum(v>0 for v in values)/len(values)*100 if values else None,
        'meanNetPct':statistics.mean(values) if values else None,'medianNetPct':statistics.median(values) if values else None,
        'profitFactor':sum(v for v in values if v>0)/loss if loss else None,
        'meanAdversePct':statistics.mean(r['adversePct'] for r in rows) if rows else None,
        'worstAdversePct':max((r['adversePct'] for r in rows),default=None),
        'positiveSymbols':sum(statistics.mean(r['netPct'] for r in rows if r['symbol']==s)>0 for s in {r['symbol'] for r in rows}),
        'doubleCostMeanPct':statistics.mean(r['grossPct']-2*r['costPct'] for r in rows) if rows else None}
def main():
    OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/'results.json').exists():raise SystemExit('Completed study exists; do not overwrite it.')
    protocol={'version':'daily-condition-study-v1','featureWindow':25,'horizons':HORIZONS,'conditions':CONDITIONS,
        'split':'2016-2022 development, 2023-2024 validation, 2025-2026 retrospective comparison',
        'priorUse':'These historical dates were used elsewhere in this project; no untouched or prospective holdout claim.',
        'execution':'signal after daily close, next actual contract open; exit close after 1/3/5/10 sessions; same contract throughout',
        'sample':'Last 25 input bars and all forward bars must have identical delivery contract; nonoverlap per symbol/condition/horizon/stage',
        'cost':'Each side max(cached per-lot commission, notional*0.0001), plus one adverse tick each side; doubled-cost sensitivity',
        'selection':'Choose horizon once on development mean net return, at least 100 events and 5 symbols; validate without reselecting',
        'promotion':'EXPLORATORY_ONLY; no live qualification from reused historical samples',
        'excluded':'Continuous-only CSV, bad roll evidence, changing contracts, zero-volume bars, overlapping events, labels crossing split boundaries',
        'sources':['https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf'],
        'sourceHash':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__),ROOT/'backtesting/trend_features.py')}}
    dump(OUT/'protocol.json',protocol)
    provider=TqSdkBacktestDataProvider(cache_dir=ROOT/'data/history/tqsdk-roll');audit=[];observations=[];groups=defaultdict(list)
    for file in sorted(provider.cache_dir.glob('*_real_roll_daily.json')):
        raw=json.loads(file.read_text(encoding='utf-8'));symbol=raw['symbol']
        if file.name!=symbol+'_real_roll_daily.json':continue
        info={'symbol':symbol,'file':file.name,'sha256':hashlib.sha256(file.read_bytes()).hexdigest()}
        try:
            ds=provider._read_cache(file,0,allow_stale=True)
            if ds is None:raise ValueError('Invalid cache schema')
            causal_prices(ds) # Audit OHLC and observed roll legs before calculating any result.
        except (ValueError,KeyError) as error:
            audit.append({**info,'status':'QUARANTINED','reason':str(error)});continue
        bars=ds.bars;last={};eligible=0
        for i in range(24,len(bars)-1):
            window=bars[i-24:i+1];contract=bars[i].contract_symbol
            if any(b.contract_symbol!=contract or b.volume<=0 for b in window):continue
            values=features([asdict(b) for b in window])
            if values is None:continue
            eligible+=1;day=bars[i].timestamp.date().isoformat();part=stage(day);spec=ds.contract_specs[contract]
            for condition in values['conditions']:
                direction=CONDITIONS[condition][1]
                for horizon in HORIZONS:
                    end=i+horizon
                    if end>=len(bars) or stage(bars[end].timestamp.date().isoformat())!=part:continue
                    future=bars[i+1:end+1]
                    if any(b.contract_symbol!=contract or b.volume<=0 for b in future):continue
                    key=(condition,horizon,part)
                    if i<=last.get(key,-1):continue
                    entry=future[0].open;exit=future[-1].close;multiple=spec.volume_multiple
                    if multiple<=0 or spec.price_tick<=0:continue
                    fees=max(spec.commission_per_lot,entry*multiple*.0001)+max(spec.commission_per_lot,exit*multiple*.0001)
                    cost=(fees/multiple+2*spec.price_tick)/entry*100
                    gross=direction*(exit/entry-1)*100
                    adverse=max(0,(entry-min(b.low for b in future))/entry*100 if direction>0 else (max(b.high for b in future)-entry)/entry*100)
                    row={'symbol':symbol,'condition':condition,'direction':direction,'horizon':horizon,'stage':part,'signalDate':day,
                        'entryDate':future[0].timestamp.date().isoformat(),'exitDate':future[-1].timestamp.date().isoformat(),
                        'contract':contract,'grossPct':gross,'costPct':cost,'netPct':gross-cost,'adversePct':adverse}
                    observations.append(row);groups[(condition,horizon,part)].append(row);last[key]=end
        audit.append({**info,'status':'AUDITED','bars':len(bars),'eligibleFeatureDays':eligible,'start':str(bars[0].timestamp.date()),'end':str(bars[-1].timestamp.date())})
    results={}
    for condition,(label,direction) in CONDITIONS.items():
        grid={str(h):{s:summarize(groups[(condition,h,s)]) for s in ('DEVELOPMENT','VALIDATION','RETROSPECTIVE_2025_2026')} for h in HORIZONS}
        eligible=[h for h in HORIZONS if grid[str(h)]['DEVELOPMENT']['samples']>=100 and grid[str(h)]['DEVELOPMENT']['symbols']>=5]
        selected=max(eligible,key=lambda h:grid[str(h)]['DEVELOPMENT']['meanNetPct']) if eligible else None
        selected_rows=grid[str(selected)] if selected else None
        gates={}
        if selected_rows:
            for s,r in selected_rows.items():gates[s]=r['samples']>=100 and r['symbols']>=5 and r['meanNetPct']>0 and r['doubleCostMeanPct']>0 and r['positiveSymbols']/r['symbols']>=.6
        results[condition]={'label':label,'direction':direction,'horizons':grid,'developmentSelectedHorizon':selected,'selected':selected_rows,
            'historicalGates':gates,'historicallyConsistent':bool(gates) and all(gates.values()),'qualification':'EXPLORATORY_ONLY'}
    report={'version':protocol['version'],'status':'EXPLORATORY_NOT_LIVE_QUALIFIED','data':audit,'eventOutcomes':len(observations),'conditions':results,
        'limitations':['Daily evidence does not validate 15-minute crossings or intraday touch alerts.','Repeated historical use; no prospective proof.',
            'Per-condition nonoverlap does not make markets or competing conditions independent.','Cached costs are assumptions, not complete historic exchange fees.',
            'Returns are separate event outcomes, not a funded portfolio; no leverage or margin model.',
            'Same-contract dominant windows imply selection and exclude rolls; not all contract lifecycles.']}
    dump(OUT/'results.json',report)
    with (OUT/'events.csv').open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(observations[0]) if observations else ['symbol']);writer.writeheader();writer.writerows(observations)
    print(json.dumps({'audited':sum(x['status']=='AUDITED' for x in audit),'quarantined':sum(x['status']=='QUARANTINED' for x in audit),'outcomes':len(observations),
        'consistentConditions':[k for k,v in results.items() if v['historicallyConsistent']]},ensure_ascii=True),flush=True)
if __name__=='__main__':main()
