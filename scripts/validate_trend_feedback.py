"""Revision two, fixed before results: matched family baselines and annual walk-forward."""
import gzip,hashlib,json,statistics,sys
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtesting.independent_research import causal_prices
from backtesting.trend_validation import EXITS,conditions,event
from data.tqsdk_backtest import TqSdkBacktestDataProvider
OUT=ROOT/'docs/research/data/trend-feedback-2026-11-07-r2'
def dump(name,value):(OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def summary(rows):
    symbols={r['symbol'] for r in rows};values=[r['netPct'] for r in rows];losses=sum(-x for x in values if x<0)
    return {'samples':len(rows),'symbols':len(symbols),'meanNetPct':statistics.mean(values) if values else None,
        'medianNetPct':statistics.median(values) if values else None,'winPct':sum(v>0 for v in values)/len(values)*100 if values else None,
        'profitFactor':sum(v for v in values if v>0)/losses if losses else None,
        'meanStressPct':statistics.mean(r['stressNetPct'] for r in rows) if rows else None,
        'worstAdversePct':max((r['adversePct'] for r in rows),default=None),
        'positiveSymbolFraction':sum(statistics.mean(r['netPct'] for r in rows if r['symbol']==s)>0 for s in symbols)/len(symbols) if symbols else 0}
def main():
    OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/'results.json').exists():raise SystemExit('Completed revision exists; never overwrite a failed attempt.')
    protocol={'version':'trend-feedback-v2','priorStudy':'trend-opportunities-2026-11-07','priorFinding':'No initial condition passed all frozen time-split gates.',
        'feedback':['Separate descriptive trend from tradable edge.','Test moderate distance/volatility and volume or candle-location confirmation.',
            'Compare to same-direction baseline with same exit and year.','Exit at observed old-contract roll open instead of using future roll survival to exclude a trade.'],
        'candidateRules':'4 families x 2 directions x 6 exits = 48; 2 directional baselines x 6 exits = 12 controls',
        'folds':'For each 2019..2026 year, select using previous three completed years only; then evaluate that year without reselecting.',
        'trainingGate':{'minimumEvents':100,'minimumSymbols':5,'meanNetPositive':True,'doubleCostPositive':True,'positiveSymbolsAtLeast':.6,'profitFactorAtLeast':1.1},
        'selection':'Highest training meanNetPct among qualifying non-baseline candidates; ties retain sorted candidate name.',
        'control':'Selected candidate and same-direction/same-exit baseline are reported side by side; not matched randomization.',
        'status':'RETROSPECTIVE_EXPLORATORY; dates reused elsewhere, not untouched holdout. Individual events not a funded portfolio.',
        'cost':'Max cached commission or notional 1bp each side, one adverse tick per side, doubled-cost sensitivity.',
        'execution':'25 same-contract input bars; next open entry; actual roll old-open exit; precommitted time close, causal MA5 next open, or stop-before-target ATR2/4; close at calendar-year boundary.',
        'sourceHashes':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),ROOT/'backtesting/trend_validation.py']}}
    dump('protocol.json',protocol)
    provider=TqSdkBacktestDataProvider(cache_dir=ROOT/'data/history/tqsdk-roll');groups=defaultdict(list);rows=[];audit=[]
    for path in sorted(provider.cache_dir.glob('*_real_roll_daily.json')):
        raw=json.loads(path.read_text(encoding='utf-8'));symbol=raw['symbol']
        if path.name!=symbol+'_real_roll_daily.json':continue
        try:
            ds=provider._read_cache(path,0,allow_stale=True)
            if ds is None:raise ValueError('Invalid dataset')
            causal_prices(ds)
        except ValueError as error:audit.append({'symbol':symbol,'status':'QUARANTINED','reason':str(error)});continue
        bars=ds.bars;year_ends={b.timestamp.year:i for i,b in enumerate(bars)};last={}
        for i in range(24,len(bars)-1):
            window=bars[i-24:i+1]
            if any(b.contract_symbol!=bars[i].contract_symbol or b.volume<=0 for b in window):continue
            year=bars[i].timestamp.year
            if bars[i+1].timestamp.year!=year:continue
            for condition,direction in conditions([asdict(b) for b in window]):
                for exit_rule in EXITS:
                    candidate=condition+'__'+exit_rule;key=(candidate,year)
                    if i<=last.get(key,-1):continue
                    value=event(ds,i,direction,exit_rule,year_ends[year])
                    if value is None:continue
                    value.update(symbol=symbol,year=year,candidate=candidate,condition=condition,exitRule=exit_rule)
                    rows.append(value);groups[(candidate,year)].append(value);last[key]=value['exitIndex']
        audit.append({'symbol':symbol,'status':'AUDITED','sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bars':len(bars)})
    names=sorted({r['candidate'] for r in rows});folds=[];selected_rows=[];control_rows=[]
    for year in range(2019,2027):
        training={name:summary([r for y in range(year-3,year) for r in groups[(name,y)]]) for name in names}
        eligible=[name for name,m in training.items() if not name.startswith('BASE_') and m['samples']>=100 and m['symbols']>=5 and m['meanNetPct']>0 and m['meanStressPct']>0 and m['positiveSymbolFraction']>=.6 and m['profitFactor'] is not None and m['profitFactor']>=1.1]
        selected=max(eligible,key=lambda name:training[name]['meanNetPct']) if eligible else None
        entry={'year':year,'trainingYears':[year-3,year-1],'selected':selected,'eligibleCandidates':len(eligible),'training':training}
        if selected:
            test=groups[(selected,year)];selected_rows+=test
            side='LONG' if selected.split('__')[0].endswith('_UP') else 'SHORT'
            baseline='BASE_'+side+'__'+selected.split('__')[1];control=groups[(baseline,year)];control_rows+=control
            entry.update(test=summary(test),control=summary(control),controlName=baseline)
        folds.append(entry)
    aggregate=summary(selected_rows);control=summary(control_rows)
    report={'version':protocol['version'],'status':'EXPLORATORY_NOT_LIVE_QUALIFIED','audits':audit,'candidateCount':len(names),
        'eventOutcomes':len(rows),'folds':folds,'selectedFoldAggregate':aggregate,'controlFoldAggregate':control,
        'positiveTestYears':sum(f.get('test',{}).get('meanNetPct',-1) is not None and f.get('test',{}).get('meanNetPct',-1)>0 for f in folds),
        'limitations':['Yearly resets and cost assumptions; no funded portfolio or historic fee certification.','Reused historical samples, no prospective qualification.',
            'Baseline controls differ in event dates/counts; no causal attribution.','Daily results do not validate 15-minute or intrabar alerts.']}
    dump('results.json',report)
    with gzip.open(OUT/'events.json.gz','wt',encoding='utf-8') as stream:json.dump(rows,stream,ensure_ascii=False,allow_nan=False)
    print(json.dumps({k:report[k] for k in ['candidateCount','eventOutcomes','selectedFoldAggregate','positiveTestYears']},ensure_ascii=True),flush=True)
if __name__=='__main__':main()
