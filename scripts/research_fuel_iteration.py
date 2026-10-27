#!/usr/bin/env python3
"""Second FU iteration: explicitly exploratory after opening the first final window."""
import csv,gzip,hashlib,json,statistics,sys
from dataclasses import asdict
from datetime import date
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtesting.fuel_iteration import FAMILIES,MODES,regime_graph
from backtesting.fuel_research import SCALES,digest,segments
from backtesting.independent_research import ResearchRisk,causal_prices,simulate
from data.tqsdk_backtest import TqSdkBacktestDataProvider
def dump(path,data):path.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def main():
    out=ROOT/'docs/research/data/fu-regime-2026-10-27'
    if (out/'manifest.json').exists():raise SystemExit('Do not overwrite an existing exploratory run')
    first=ROOT/'docs/research/data/fu-focused-2026-10-27-r2'
    prior=json.loads((first/'manifest.json').read_text(encoding='utf-8'))
    with gzip.open(first/'source-snapshot.json.gz','rb') as stream:raw=stream.read()
    source=ROOT/'.test-tmp/fu-research-input.json'
    assert source.read_bytes()==raw
    provider=TqSdkBacktestDataProvider(cache_dir=ROOT/'.test-tmp');data=provider._read_cache(source,0,allow_stale=True)
    signals=causal_prices(data);risk=ResearchRisk()
    graphs={(f,m,s):regime_graph(f,m,s) for f in FAMILIES for m in MODES for s in SCALES}
    paths=['backtesting/fuel_iteration.py','backtesting/fuel_research.py','backtesting/independent_research.py',
           'backtesting/workflow.py','backtesting/backtester.py','scripts/research_fuel_iteration.py',
           'docs/plans/2026-10-27-fu-regime-iteration.md']
    out.mkdir(parents=True,exist_ok=True)
    dump(out/'manifest.json',{'status':'POST_FINAL_EXPLORATORY_NOT_NEW_OUT_OF_SAMPLE',
      'sourceSha256':hashlib.sha256(raw).hexdigest(),'previousExperiment':str(first.relative_to(ROOT)),
      'risk':asdict(risk),'windows':prior['windows'],'graphs':{'__'.join(map(str,k)):v for k,v in graphs.items()},
      'codeAndProtocolHashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths},
      'selection':'Centers only; development trades>=20, median segment Sharpe, then net PnL. Validation cannot choose.',
      'forwardEvidenceRequiredAfter':str(data.bars[-1].timestamp.date())})
    records=[];ledgers=[];cache={}
    def run(stage,family,mode,scale=1.,capital=1_000_000,cost=1):
        key=(stage,family,mode,scale,capital,cost)
        if key in cache:return cache[key]
        a,b=map(date.fromisoformat,prior['windows'][stage])
        result=simulate(data,graphs[(family,mode,scale)],capital,a,b,risk=risk,cost_multiplier=cost,signals=signals)
        row={'stage':stage,'family':family,'mode':mode,'scale':scale,'capital':capital,'cost':cost,
             'metrics':result['metrics'],'segments':segments(result['curve'],capital),'graphHash':digest(graphs[(family,mode,scale)])}
        records.append(row);ledgers.append({'key':list(key),'result':result});cache[key]=row
        return row
    for f,m,s in graphs:
        for cost in (1,2):run('DEVELOPMENT',f,m,s,cost=cost)
    centers=[r for r in records if r['scale']==1. and r['cost']==1]
    chosen=max(centers,key=lambda r:(r['metrics']['closedTrades']>=20,statistics.median(s['sharpe'] for s in r['segments']),r['metrics']['netPnl']))
    dump(out/'selection-before-validation.json',chosen)
    for stage in ('VALIDATION','FINAL'):
        for f,m,s in graphs:
            for cost in (1,2):run(stage,f,m,s,cost=cost)
        for capital in (10_000,100_000):
            for cost in (1,2):run(stage,chosen['family'],chosen['mode'],capital=capital,cost=cost)
    rows={stage:{str(cost):cache[(stage,chosen['family'],chosen['mode'],1.,1_000_000,cost)]['metrics']
                 for cost in (1,2)} for stage in prior['windows']}
    report={'status':'EXPLORATORY_REQUIRES_NEW_FORWARD_DATA','runCount':len(records),
       'selectedByDevelopment':chosen,'selectedResults':rows,'noIndependentValidationClaim':True,
       'nextStep':'Freeze this observation candidate; prior final data cannot be reused as fresh evidence.'}
    dump(out/'results.json',report);dump(out/'all-runs.json',records)
    with gzip.open(out/'full-ledgers.json.gz','wt',encoding='utf-8') as stream:json.dump(ledgers,stream,ensure_ascii=False,allow_nan=False)
    dump(out/'observation-candidate.json',{'qualification':'EXPLORATORY_DIAGNOSTIC_ONLY','selected':chosen,
        'definition':graphs[(chosen['family'],chosen['mode'],1.)],'risk':asdict(risk),'asOf':str(data.bars[-1].timestamp.date()),
        'state':'WAITING_FOR_NEW_FU_DATA','futureOrdersOrFills':[],'sourceSha256':hashlib.sha256(raw).hexdigest(),
        'signalBasis':'CAUSAL_DELIVERY_ROLL_RATIO','execution':'Research risk budget, not existing fixed-lot workflow semantics'})
    flat=[{**{k:v for k,v in r.items() if k not in ('metrics','segments')},
           **{k:v for k,v in r['metrics'].items() if k!='denials'},'denials':json.dumps(r['metrics']['denials'])} for r in records]
    with (out/'all-runs.csv').open('w',newline='',encoding='utf-8-sig') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(flat[0]));writer.writeheader();writer.writerows(flat)
    print(json.dumps({'runs':len(records),'chosen':(chosen['family'],chosen['mode']),'metrics':rows}),flush=True)
if __name__=='__main__':main()
