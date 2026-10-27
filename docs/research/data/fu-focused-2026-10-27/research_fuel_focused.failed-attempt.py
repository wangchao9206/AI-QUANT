#!/usr/bin/env python3
"""FU-only staged research with a fixed selection boundary and complete failure records."""
import argparse,csv,gzip,hashlib,json,math,statistics,sys
from collections import Counter
from dataclasses import asdict
from datetime import date,datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtesting.fuel_research import (ENGINE,FAMILIES,SCALES,REPAIRS,build,digest,segments,
    adjusted_sharpe_p,choose_candidates,delayed_signals)
from backtesting.independent_research import ResearchRisk,causal_prices,simulate
from data.tqsdk_backtest import TqSdkBacktestDataProvider

CORE=1_000_000
CAPITALS=(10_000,100_000,CORE)

def dump(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')

def id_of(family,repair,scale=1.,direction='BOTH'):
    return family+'__'+repair+'__'+str(scale)+'__'+direction

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--input',default='.test-tmp/fu-research-input.json')
    parser.add_argument('--output',default='docs/research/data/fu-focused-2026-10-27')
    args=parser.parse_args();out=ROOT/args.output
    if (out/'manifest.json').exists():raise SystemExit('Frozen experiment exists; preserve it and use a new attempt directory.')
    raw=(ROOT/args.input).read_bytes();raw_json=json.loads(raw)
    provider=TqSdkBacktestDataProvider(cache_dir=ROOT/'.test-tmp')
    data=provider._read_cache(ROOT/args.input,0,allow_stale=True)
    if data is None or data.symbol!='FU0' or not data.complete:raise ValueError('Complete FU0 evidence required')
    signals=causal_prices(data)
    if any(s.volume_multiple!=10 or s.price_tick!=1 for s in data.contract_specs.values()):raise ValueError('FU specifications disagree with exchange contract')
    if any(b.volume<0 or b.timestamp.tzinfo is None for b in data.bars):raise ValueError('Invalid observation')
    if len(data.bars)<1000:raise ValueError('Expanded history required for this frozen protocol')
    risk=ResearchRisk()
    windows={'DEVELOPMENT':(data.bars[80].timestamp.date(),date(2023,12,31)),
             'VALIDATION':(date(2024,1,1),date(2025,12,31)),
             'FINAL':(date(2026,1,1),data.bars[-1].timestamp.date())}
    graphs={id_of(f,r,s):build(f,s,r) for f in FAMILIES for r in REPAIRS for s in SCALES}
    out.mkdir(parents=True,exist_ok=True)
    source_hash=hashlib.sha256(raw).hexdigest()
    with gzip.open(out/'source-snapshot.json.gz','wb') as stream:stream.write(raw)
    paths=[ROOT/'backtesting/fuel_research.py',ROOT/'scripts/research_fuel_focused.py',
           ROOT/'backtesting/independent_research.py',ROOT/'backtesting/workflow.py',ROOT/'backtesting/backtester.py',
           ROOT/'docs/plans/2026-10-27-fu-focused-research.md']
    manifest={'protocol':'fu-focused-2026-10-27','engineVersion':ENGINE,'createdAt':datetime.now().astimezone().isoformat(),
        'source':{'symbol':data.symbol,'provider':data.provider_symbol,'source':data.source,'sha256':source_hash,
                  'bars':len(data.bars),'rolls':len(data.roll_events),'contracts':len(data.contract_specs),
                  'first':str(data.bars[0].timestamp.date()),'last':str(data.bars[-1].timestamp.date())},
        'windows':{k:[str(a),str(b)] for k,(a,b) in windows.items()},'risk':asdict(risk),
        'capital':CORE,'comparisonCapitals':CAPITALS,'scales':SCALES,'repairs':REPAIRS,
        'families':FAMILIES,'graphs':graphs,'developmentConfigCount':len(graphs),
        'codeAndProtocolHashes':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        'selection':'development only, stable center and predeclared repair conditions; three distinct mechanisms',
        'finalOpensOnce':True,'priorUse':'2025 and some 2026 data may have appeared in other research; not forward evidence',
        'delayDefinition':'one-bar lag on signal features; latest observed execution ATR for risk, same next-open matching',
        'fees':'max(snapshot commission, .0001 notional), 1 tick market slippage; multiply both by stress cost',
        'promotionGates':{'developmentTrades':30,'positiveDevSegments':2,'stressPositiveNeighbors':2,
                         'validationTrades':15,'finalTrades':8,'maxCloseDrawdownPct':8,
                         'positiveBaseAnd2xCosts':True,'profitExcludingBestTradePositive':True,'adjustedPAtMost':.1}}
    dump(out/'manifest.json',manifest)
    print(json.dumps({'phase':'FROZEN','mechanisms':len(FAMILIES),'configurations':len(graphs),'bars':len(data.bars)}),flush=True)
    records=[];ledgers=[];cache={}
    def run(stage,family,repair,scale=1.,capital=CORE,cost=1,direction='BOTH',delay=False):
        key=(stage,family,repair,scale,capital,cost,direction,delay)
        if key in cache:return cache[key]
        graph=graphs[id_of(family,repair,scale)] if direction=='BOTH' else build(family,scale,repair,direction)
        a,b=windows[stage]
        result=simulate(data,graph,capital,a,b,cost_multiplier=cost,risk=risk,
                        signals=delayed_signals(signals) if delay else signals)
        row={'stage':stage,'family':family,'repair':repair,'scale':scale,'capital':capital,'cost':cost,
             'direction':direction,'signalDelay':delay,'configId':id_of(family,repair,scale,direction),
             'graphHash':digest(graph),'metrics':result['metrics'],'segments':segments(result['curve'],capital)}
        records.append(row);ledgers.append({'key':list(key),'result':result})
        cache[key]=row
        if len(records)%25==0:print(json.dumps({'phase':stage,'completedRuns':len(records)}),flush=True)
        return row
    # Phase 1: actual baseline mechanisms, all 16, independent of early failures.
    for family in FAMILIES:
        for cost in (1,2):run('DEVELOPMENT',family,'BASE',cost=cost)
    dump(out/'round-1-baselines.json',records)
    # Phase 2: all predeclared repairs and neighboring scales, no adaptive parameter search.
    for family in FAMILIES:
        for repair in REPAIRS:
            for scale in SCALES:
                for cost in (1,2):run('DEVELOPMENT',family,repair,scale,cost=cost)
        for side in ('LONG','SHORT'):run('DEVELOPMENT',family,'BASE',direction=side)
    selected,all_families=choose_candidates(records)
    dump(out/'development-selection.json',{'selected':selected,'allFamilyCenters':all_families,
        'selectionFrozenBeforeValidation':True})
    development_curves={id_of(l['key'][1],l['key'][2],l['key'][3]):l['result']['curve']
        for l in ledgers if l['key'][0]=='DEVELOPMENT' and l['key'][5]==1 and l['key'][6]=='BOTH'}
    selected_ids=[id_of(s['family'],s['repair']) for s in selected]
    multiple=adjusted_sharpe_p(development_curves,CORE,selected_ids)
    dump(out/'multiple-testing.json',multiple)
    print(json.dumps({'phase':'SELECTION_FROZEN','selected':selected,'bootstrap':multiple}),flush=True)
    # Phase 3 and 4: evaluate the SAME three. Never substitute a validation winner.
    for stage in ('VALIDATION','FINAL'):
        dump(out/(stage.lower()+'-opened.json'),{'openedAt':datetime.now().astimezone().isoformat(),'selected':selected_ids})
        for choice in selected:
            f,r=choice['family'],choice['repair']
            for capital in CAPITALS:
                for cost in (1,2):run(stage,f,r,capital=capital,cost=cost)
            run(stage,f,r,cost=4)
            for scale in (.75,1.25):
                for cost in (1,2):run(stage,f,r,scale,cost=cost)
            for cost in (1,2):run(stage,f,r,cost=cost,delay=True)
    def record(stage,choice,cost=1,capital=CORE):
        return cache[(stage,choice['family'],choice['repair'],1.,capital,cost,'BOTH',False)]
    outcomes=[]
    for choice in selected:
        a=record('VALIDATION',choice)['metrics'];b=record('FINAL',choice)['metrics']
        a2=record('VALIDATION',choice,2)['metrics'];b2=record('FINAL',choice,2)['metrics']
        relevant=[l for l in ledgers if l['key'][0] in ('VALIDATION','FINAL') and l['key'][1:4]==[choice['family'],choice['repair'],1.]
                  and l['key'][4:]==[CORE,1,'BOTH',False]]
        exclude_best={l['key'][0]:sum(t['netPnl'] for t in l['result']['trades'])-max(
            (t['netPnl'] for t in l['result']['trades']),default=0) for l in relevant}
        p=multiple['selected'][id_of(choice['family'],choice['repair'])]['adjustedP']
        gates={'development':choice['developmentQualified'],'validationSample':a['closedTrades']>=15,
            'finalSample':b['closedTrades']>=8,'validationNet':a['netPnl']>0,'finalNet':b['netPnl']>0,
            'doubleCost':a2['netPnl']>0 and b2['netPnl']>0,
            'closeDrawdown':max(a['maxDrawdownPct'],b['maxDrawdownPct'])<=8,
            'excludeBest':all(exclude_best.get(s,0)>0 for s in ('VALIDATION','FINAL')),
            'multipleTesting':p<=.1}
        outcomes.append({**choice,'validation':a,'validation2x':a2,'final':b,'final2x':b2,
            'excludeBest':exclude_best,'adjustedP':p,'gates':gates,'observationQualified':all(gates.values())})
    journal=[]
    for family in FAMILIES:
        def dev(repair,scale=1.,cost=1):
            return cache[('DEVELOPMENT',family,repair,scale,CORE,cost,'BOTH',False)]
        base=dev('BASE');repair_rows={r:dev(r) for r in REPAIRS[1:]}
        diagnoses=[]
        if base['metrics']['netPnl']<=0:diagnoses.append('基准扣费净亏')
        if dev('BASE',cost=2)['metrics']['netPnl']<=0:diagnoses.append('双倍成本不盈利')
        if base['metrics']['closedTrades']<30:diagnoses.append('开发交易样本不足30')
        if sum(s['returnPct']>0 for s in base['segments'])<2:diagnoses.append('盈利不覆盖多数开发分段')
        if sum(dev('BASE',scale=s,cost=2)['metrics']['netPnl']>0 for s in SCALES)<2:diagnoses.append('邻近尺度不稳')
        journal.append({'family':family,'name':FAMILIES[family][0],'hypothesis':FAMILIES[family][1],
            'base':base['metrics'],'base2x':dev('BASE',cost=2)['metrics'],'segments':base['segments'],
            'failureReasons':diagnoses or ['开发诊断未发现上述失败；仍须后续检验'],
            'repairs':{r:{'metrics':v['metrics'],'basePnlDifference':v['metrics']['netPnl']-base['metrics']['netPnl'],
                          'stressPnl':dev(r,cost=2)['metrics']['netPnl']} for r,v in repair_rows.items()},
            'lesson':'按预先定义修正核对失败来源；改善开发成绩不等于通过后续验证'})
    report={'engineVersion':ENGINE,'runCount':len(records),'mechanisms':len(FAMILIES),
        'developmentConfigurations':len(graphs),'selected':outcomes,'familyJournal':journal,
        'qualifiedCount':sum(o['observationQualified'] for o in outcomes),
        'finalSelectionUnchanged':True,'status':'FORWARD_OBSERVATION_ONLY' if any(o['observationQualified'] for o in outcomes)
            else 'CONTINUE_RESEARCH_NO_QUALIFIED_RULE','sourceSha256':source_hash}
    dump(out/'results.json',report);dump(out/'failure-journal.json',journal)
    flat=[]
    for r in records:
        m=r['metrics'];flat.append({**{k:v for k,v in r.items() if k not in ('metrics','segments')},
            **{k:v for k,v in m.items() if k!='denials'},'denials':json.dumps(m['denials'],sort_keys=True)})
    with (out/'all-runs.csv').open('w',newline='',encoding='utf-8-sig') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(flat[0]));writer.writeheader();writer.writerows(flat)
    with gzip.open(out/'full-ledgers.json.gz','wt',encoding='utf-8') as stream:json.dump(ledgers,stream,ensure_ascii=False,allow_nan=False)
    for item in selected:
        key=id_of(item['family'],item['repair'])
        dump(out/(key+'.json'),{'status':'RESEARCH_GRAPH_NOT_PRODUCTION_SIZING',
            'config':item,'definition':graphs[key],'risk':asdict(risk),'signalBasis':'CAUSAL_DELIVERY_ROLL_RATIO'})
    # Next-bar observation plan is a frozen research plan, never a fabricated fill.
    dump(out/'next-observation-plan.json',{'asOf':str(data.bars[-1].timestamp.date()),
        'earliestNewTradingDateAfter':str(data.bars[-1].timestamp.date()),
        'status':'AWAIT_NEW_OBSERVATIONS','candidates':[{'family':o['family'],'repair':o['repair'],
            'graphHash':o['graphHash'],'qualification':'OBSERVATION_QUALIFIED' if o['observationQualified'] else 'DIAGNOSTIC_ONLY'}
            for o in outcomes],'noNewOrderOrFillCreated':True,
        'required':'Append independently audited new FU delivery bars and both roll legs before evaluating; keep these choices frozen.'})
    plot(out,records,ledgers,selected)
    print(json.dumps({'phase':'COMPLETE','runs':len(records),'observationQualified':report['qualifiedCount'],
                      'candidates':[(o['family'],o['repair'],o['gates']) for o in outcomes]}),flush=True)

def plot(out,records,ledgers,selected):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,1,figsize=(14,10),layout='constrained')
    base=[r for r in records if r['stage']=='DEVELOPMENT' and r['repair']=='BASE' and r['scale']==1.
          and r['direction']=='BOTH' and r['cost']==1]
    x=range(len(base))
    axes[0].bar(x,[r['metrics']['returnPct'] for r in base],color=['#357b72' if r['metrics']['returnPct']>0 else '#b46556' for r in base])
    axes[0].set_xticks(list(x),[r['family'] for r in base],rotation=45,ha='right',fontsize=8)
    axes[0].axhline(0,color='#aaa',lw=.7);axes[0].set_ylabel('Development net return (%)')
    for choice in selected:
        for stage,style in [('VALIDATION','-'),('FINAL','--')]:
            r=next(l for l in ledgers if l['key']==[stage,choice['family'],choice['repair'],1.,CORE,1,'BOTH',False])
            axes[1].plot([p['date'] for p in r['result']['curve']],
                         [(p['equity']/CORE-1)*100 for p in r['result']['curve']],
                         linestyle=style,label=choice['family']+' / '+stage)
    axes[1].xaxis.set_major_locator(plt.MaxNLocator(8));axes[1].tick_params(axis='x',rotation=20)
    axes[1].set_ylabel('Window net return (%)');axes[1].legend(fontsize=8,ncol=2)
    axes[1].axhline(0,color='#aaa',lw=.7)
    fig.suptitle('FU only | fixed 16 hypotheses, 144 declared configurations | conditional historical simulations')
    fig.savefig(out/'research.png',dpi=150);plt.close(fig)

if __name__=='__main__':main()
