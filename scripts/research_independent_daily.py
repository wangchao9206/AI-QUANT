#!/usr/bin/env python3
"""One frozen daily experiment; no production writes and no parameter optimizer."""
from __future__ import annotations
import argparse,csv,gzip,hashlib,json,statistics,sys
from collections import Counter
from dataclasses import asdict
from datetime import date,datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backtesting.independent_research import ENGINE,ResearchRisk,causal_prices,hypothesis,simulate
from data.tqsdk_backtest import TqSdkBacktestDataProvider

FAMILIES=('BREAKOUT','PULLBACK','REVERSION')
CAPITALS=(10_000,100_000,1_000_000)
CORE=1_000_000
NAMES={'BREAKOUT':'顺势区间突破','PULLBACK':'顺大趋势的短期回撤','REVERSION':'无趋势过滤的均值回归'}

def dump(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')

def summary(rows):
    n=len(rows);active=[r for r in rows if r['closedTrades']>0]
    gains=sum(r['grossNetWinners'] for r in rows);losses=sum(r['grossNetLosers'] for r in rows)
    return {'accounts':n,'activeAccounts':len(active),'closedTrades':sum(r['closedTrades'] for r in rows),
        'positiveAccounts':sum(r['netPnl']>0 for r in rows),
        'positiveFraction':sum(r['netPnl']>0 for r in rows)/n if n else 0,
        'medianReturnPct':statistics.median(r['returnPct'] for r in rows) if n else 0,
        'meanReturnPct':statistics.mean(r['returnPct'] for r in rows) if n else 0,
        'medianSharpeAll':statistics.median(r['sharpe'] for r in rows) if n else 0,
        'medianSharpeActive':statistics.median(r['sharpe'] for r in active) if active else 0,
        'worstAccountDrawdownPct':max((r['maxDrawdownPct'] for r in rows),default=0),
        'sumNetPnlSeparateAccounts':sum(r['netPnl'] for r in rows),
        'netTradeProfitFactor':gains/losses if losses else None,
        'overBudgetExits':sum(r['overBudgetExits'] for r in rows),
        'oneLotDenials':sum(r['denials'].get('RISK_OR_MARGIN_BELOW_ONE_LOT',0) for r in rows)}

def write_csv(path,rows):
    flat=[{**{k:v for k,v in r.items() if k!='denials'},'denials':json.dumps(r['denials'],sort_keys=True)} for r in rows]
    with path.open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(flat[0]));writer.writeheader();writer.writerows(flat)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',default='docs/research/data/independent-daily-2026-10-27')
    args=parser.parse_args();out=(ROOT/args.output).resolve();out.mkdir(parents=True,exist_ok=True)
    if (out/'results.json').exists():raise SystemExit('Completed experiment exists; do not overwrite or silently rerun.')
    provider=TqSdkBacktestDataProvider(cache_dir=ROOT/'data/history/tqsdk-roll')
    datasets={};signals={};inventory=[];quarantined=[]
    for p in sorted(provider.cache_dir.glob('*_real_roll_daily.json')):
        raw=p.read_bytes();d=json.loads(raw);symbol=d['symbol']
        ds=provider.cached_replay(symbol)
        if ds is None:raise ValueError('Invalid real dataset: '+symbol)
        try:normalized=causal_prices(ds) # Audit before computing any strategy outcome.
        except ValueError as error:
            quarantined.append({'symbol':symbol,'reason':str(error),'file':p.name,'sha256':hashlib.sha256(raw).hexdigest()})
            continue
        before=[b for b in ds.bars if b.timestamp.date()<date(2025,1,1)]
        median=statistics.median(b.volume for b in before[-60:]) if len(before)>=60 else None
        exchange=ds.provider_symbol.split('@')[-1].split('.')[0]
        eligible=exchange!='CFFEX' and median is not None and median>=10_000
        datasets[symbol]=ds;signals[symbol]=normalized
        inventory.append({'symbol':symbol,'file':p.name,'sha256':hashlib.sha256(raw).hexdigest(),
            'bars':len(ds.bars),'start':str(ds.bars[0].timestamp.date()),'end':str(ds.bars[-1].timestamp.date()),
            'pre2025Bars':len(before),'pre2025MedianVolume60':median,'exchange':exchange,'validationEligible':eligible,
            'trainingEligible':exchange!='CFFEX' and len(before)>=1000,'source':ds.source,
            'rolls':len(ds.roll_events),'signalBasis':'CAUSAL_DELIVERY_ROLL_RATIO'})
    if len({r['symbol'] for r in inventory})!=len(inventory):raise ValueError('Ambiguous duplicate symbol snapshots')
    universe=[r['symbol'] for r in inventory if r['validationEligible']]
    train=[r['symbol'] for r in inventory if r['trainingEligible']]
    risk=ResearchRisk()
    protocol={'engineVersion':ENGINE,'createdAt':datetime.now().astimezone().isoformat(),
        'protocol':'2026-10-27-first-independent-daily-revision-2','developmentEnd':'2024-12-31',
        'validation':['2025-01-01','2025-12-31'],'lockedHoldout':['2026-01-01','2026-10-16'],
        'capitals':CAPITALS,'coreCapital':CORE,'costMultipliers':[1,2],'risk':asdict(risk),
        'trainingSymbols':train,'validationSymbols':universe,
        'modelDefinitions':{family:hypothesis(family) for family in FAMILIES},
        'neighborhood':[{'period':15,'stop':2},{'period':25,'stop':2},{'period':20,'stop':1.5},{'period':20,'stop':2.5}],
        'selection':'Maximum development medianSharpeAll at coreCapital, base cost; ties retain family order.',
        'developmentGates':{'positiveFraction':2/3,'closedTrades':30,'medianSharpeAllGreaterThan':0},
        'validationGates':{'closedTrades':100,'positiveFraction':.5,'medianSharpeActive':.2,
            'netTradeProfitFactor':1.1,'worstAccountDrawdownPctAtMost':10,
            'stressPositiveFraction':.5,'stressSeparateAccountTotalPositive':True,'positiveNeighborsAtLeast':3},
        'data':inventory,'quarantined':quarantined,
        'revisionReason':'Before any strategy evaluation: M0/CJ0/LC0 roll-new-open differs from execution-bar-open; exclude rather than patch. Only RB0 remains development eligible.',
        'priorUseCaveat':'2026 was used elsewhere in the project; this is only a held-back window within this experiment, not untouched or forward evidence.',
        'executionPolicy':'ResearchRisk budget sizing, not the graph RISK.lots placeholder',
        'codeSha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [Path(__file__),ROOT/'backtesting/independent_research.py',ROOT/'backtesting/workflow.py',ROOT/'backtesting/backtester.py']}}
    manifest=out/'manifest.json'
    if manifest.exists():raise SystemExit('Existing manifest: inspect before starting a different attempt.')
    dump(manifest,protocol)
    source_audit=ROOT/'.test-tmp/independent-data-audit-failures.json'
    if source_audit.exists():dump(out/'data-conflicts.json',json.loads(source_audit.read_text(encoding='utf-8')))
    print(json.dumps({'phase':'PRE_REGISTERED','symbols':len(universe),'training':train,'holdoutOpened':False}),flush=True)
    records=[];details=[];cache={}
    def execute(stage,family,symbol,capital,cost,period=20,stop=2):
        key=(stage,family,symbol,capital,cost,period,stop)
        if key in cache:return cache[key]
        ds=datasets[symbol]
        start,end=(ds.bars[0].timestamp.date(),date(2024,12,31)) if stage=='DEVELOPMENT' else (
            (date(2025,1,1),date(2025,12,31)) if stage=='VALIDATION' else (date(2026,1,1),date(2026,10,16)))
        result=simulate(ds,hypothesis(family,period,stop),capital,start,end,cost_multiplier=cost,risk=risk,signals=signals[symbol])
        record={'stage':stage,'family':family,'symbol':symbol,'capital':capital,'costMultiplier':cost,
                'period':period,'stopAtr':stop,**result['metrics']}
        records.append(record);details.append({'key':list(key),**result});cache[key]=record
        if len(records)%50==0:print(json.dumps({'phase':stage,'completedRuns':len(records)}),flush=True)
        return record
    def group(stage,family,capital=CORE,cost=1,period=20,stop=2):
        return [r for r in records if (r['stage'],r['family'],r['capital'],r['costMultiplier'],r['period'],r['stopAtr'])==
                (stage,family,capital,cost,period,stop)]
    for family in FAMILIES:
        for capital in CAPITALS:
            for cost in (1,2):
                for symbol in train:execute('DEVELOPMENT',family,symbol,capital,cost)
    development={f:summary(group('DEVELOPMENT',f)) for f in FAMILIES}
    selected=max(FAMILIES,key=lambda f:development[f]['medianSharpeAll'])
    ds=development[selected]
    development_pass=ds['positiveFraction']>=2/3 and ds['closedTrades']>=30 and ds['medianSharpeAll']>0
    dump(out/'development-selection.json',{'selectedOnce':selected,'developmentPassed':development_pass,'all':development})
    print(json.dumps({'phase':'DEVELOPMENT_FINISHED','selected':selected,'passed':development_pass,'metrics':ds}),flush=True)
    # All three base models are frozen comparisons. Validation never changes selection.
    for family in FAMILIES:
        for capital in CAPITALS:
            for cost in (1,2):
                for symbol in universe:execute('VALIDATION',family,symbol,capital,cost)
    neighbors=[]
    for settings in protocol['neighborhood']:
        for symbol in universe:execute('VALIDATION',selected,symbol,CORE,1,settings['period'],settings['stop'])
        neighbors.append({**settings,'summary':summary(group('VALIDATION',selected,CORE,1,settings['period'],settings['stop']))})
    v=summary(group('VALIDATION',selected));stress=summary(group('VALIDATION',selected,cost=2))
    gates={'development':development_pass,'trades':v['closedTrades']>=100,'breadth':v['positiveFraction']>=.5,
        'medianSharpe':v['medianSharpeActive']>=.2,'netProfitFactor':v['netTradeProfitFactor'] is not None and v['netTradeProfitFactor']>=1.1,
        'maxDrawdown':v['worstAccountDrawdownPct']<=10,
        'stressTotal':stress['sumNetPnlSeparateAccounts']>0,'stressBreadth':stress['positiveFraction']>=.5,
        'neighbors':sum(n['summary']['sumNetPnlSeparateAccounts']>0 for n in neighbors)>=3}
    opened=all(gates.values())
    validation={f:{str(c):{str(k):summary(group('VALIDATION',f,c,k)) for k in (1,2)} for c in CAPITALS} for f in FAMILIES}
    holdout={}
    if opened:
        print(json.dumps({'phase':'HOLDOUT_UNLOCKED','selected':selected}),flush=True)
        for capital in CAPITALS:
            for cost in (1,2):
                for symbol in universe:execute('HOLDOUT',selected,symbol,capital,cost)
        holdout={str(c):{str(k):summary(group('HOLDOUT',selected,c,k)) for k in (1,2)} for c in CAPITALS}
    report={'selectedFamily':selected,'familyNames':NAMES,'development':development,'developmentPassed':development_pass,
        'validation':validation,'neighbors':neighbors,'gates':gates,'holdoutOpened':opened,'holdout':holdout,
        'runCount':len(records),'status':'HOLDOUT_EVALUATED_NOT_LIVE_VALIDATED' if opened else 'NOT_PROMOTED_HOLDOUT_REMAINS_LOCKED',
        'independentAccountsNotPortfolio':True}
    dump(out/'results.json',report);write_csv(out/'all-runs.csv',records)
    with gzip.open(out/'full-ledgers.json.gz','wt',encoding='utf-8') as stream:json.dump(details,stream,ensure_ascii=False,allow_nan=False)
    plot(out,selected,records,universe)
    print(json.dumps({'phase':'COMPLETE','runs':len(records),'selected':selected,'gates':gates,'holdoutOpened':opened}),flush=True)

def plot(out,selected,records,symbols):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(14,5),layout='constrained')
    core=[r for r in records if r['stage']=='VALIDATION' and r['family']==selected and r['capital']==CORE
          and r['period']==20 and r['stopAtr']==2]
    base={r['symbol']:r for r in core if r['costMultiplier']==1}
    stress={r['symbol']:r for r in core if r['costMultiplier']==2}
    axes[0].scatter([base[s]['returnPct'] for s in symbols],[stress[s]['returnPct'] for s in symbols],color='#386c75',s=30)
    axes[0].axhline(0,color='#aaa',lw=.7);axes[0].axvline(0,color='#aaa',lw=.7)
    axes[0].set(xlabel='Base cost net return (%)',ylabel='2x cost net return (%)',title='2025 validation: every fixed-universe account')
    for s in symbols:
        if s in ('JM0','J0','M0','RB0','CJ0'):
            axes[0].annotate(s,(base[s]['returnPct'],stress[s]['returnPct']),fontsize=8)
    for i,capital in enumerate(CAPITALS):
        r=[r['returnPct'] for r in records if r['stage']=='VALIDATION' and r['family']==selected and r['capital']==capital
           and r['costMultiplier']==1 and r['period']==20 and r['stopAtr']==2]
        axes[1].scatter([i+(j%7-3)*.025 for j in range(len(r))],r,alpha=.6,color='#386c75',s=20)
        axes[1].plot([i-.15,i+.15],[statistics.median(r)]*2,color='#b65d4a',lw=3)
    axes[1].set_xticks(range(3),['CNY 10,000','CNY 100,000','CNY 1,000,000'])
    axes[1].axhline(0,color='#aaa',lw=.7);axes[1].set(ylabel='Net return per independent account (%)',title='Same risk rules; zero-trade accounts included')
    fig.suptitle('Frozen daily hypotheses | 2025 validation | '+selected+' | not a live return forecast')
    fig.savefig(out/'validation.png',dpi=160);plt.close(fig)

if __name__=='__main__':main()
