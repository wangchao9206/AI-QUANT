"""Audit exact labels, live eligibility, stress costs and conditional Chan ablations.

No refitting or candidate reranking. Every training-selected path is retained.
"""
import bisect,gzip,hashlib,json,random,statistics,sys
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from backtesting.outcome_features import targets,matches
from backtesting.multifactor_features import stamp,FAMILIES
from research_multifactor_chan import OUT,PARTS,grade,dump
from discover_outcome_patterns import summarize

def paired(rows,path,technical,label):
    controls=[r for r in rows if matches(r['feature'],technical)]
    selected=[r for r in controls if matches(r['feature'],path)]
    if not controls or not selected:return {'samples':len(selected),'controlSamples':len(controls),'differencePp':None,'intervalPp':None}
    difference=100*(statistics.mean(r['labels'][label] for r in selected)-statistics.mean(r['labels'][label] for r in controls))
    blocks=defaultdict(lambda:[0,0,0,0])
    for r in controls:
        b=blocks[r['week']];b[0]+=1;b[1]+=r['labels'][label]
        if matches(r['feature'],path):b[2]+=1;b[3]+=r['labels'][label]
    values=list(blocks.values());draws=[];rng=random.Random(17)
    if len(values)>=8:
        for _ in range(500):
            totals=[0,0,0,0]
            for _ in values:
                item=values[rng.randrange(len(values))]
                totals=[a+b for a,b in zip(totals,item)]
            if totals[0] and totals[2]:draws.append(100*(totals[3]/totals[2]-totals[1]/totals[0]))
    draws.sort()
    return {'samples':len(selected),'controlSamples':len(controls),'differencePp':difference,
            'weeks':len(values),'intervalPp':[draws[int(.025*len(draws))],draws[min(len(draws)-1,int(.975*len(draws)))]] if len(draws)>=400 else None}

def trade(entry,future,atr,tick,direction):
    stop=entry-direction*atr;target=entry+direction*2*atr;exit=future[-1]['price']
    for b in future:
        if direction*(b['open']-stop)<=0:exit=b['open'];break
        if direction*(b['open']-target)>=0:exit=target;break
        if b['low']<=stop if direction>0 else b['high']>=stop:exit=stop;break
        if b['high']>=target if direction>0 else b['low']<=target:exit=target;break
    cost=((entry+exit)*.0001+2*tick)/entry*100
    return direction*(exit/entry-1)*100-cost,cost

def main():
    if (OUT/'live-eligibility-audit.json').exists():raise SystemExit('Completed audit exists; do not overwrite')
    registration={'scope':'Fixed additional safety eligibility: preceding20 completed daily volume median>=10000; same threshold on all paths and controls. No refitting or reranking.',
                  'reason':'Discovery cohort selects currently active contracts. Live monitor also checks current historical daily activity. Report this additional conditioning explicitly.',
                  'discoveryProtocolSha256':hashlib.sha256((OUT/'protocol.json').read_bytes()).hexdigest(),
                  'auditCodeSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    dump('audit-protocol.json',registration)
    protocol=json.loads((OUT/'protocol.json').read_text(encoding='utf-8'));result=json.loads((OUT/'results.json').read_text(encoding='utf-8'))
    for name,expected in protocol['codeHashes'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==expected,name
    with gzip.open(OUT/'decisions.json.gz','rt',encoding='utf-8') as stream:rows=json.load(stream)
    sources={};indexes={};daytimes={}
    for item in result['inventory']:
        path=ROOT/'data/history/intraday-active-study'/item['file'];assert hashlib.sha256(path.read_bytes()).hexdigest()==item['sha256']
        source=json.loads(path.read_text(encoding='utf-8'));sources[source['contract']]=source
        indexes[source['contract']]={b['timestamp']:i for i,b in enumerate(source['bars15m'])}
        daytimes[source['contract']]=[stamp(b['timestamp']) for b in source['barsDaily']]
    ledger=[];qualified=[]
    for r in rows:
        source=sources[r['contract']];m=source['bars15m'];d=source['barsDaily'];i=indexes[r['contract']][r['signalAt']]
        j=bisect.bisect_right(daytimes[r['contract']],stamp(r['confirmedAt']))-1
        atr=r['feature']['m15.atrPct']*m[i]['price']/100
        label=targets(m[i],m[:i],m[i+1:i+17],atr,source['priceTick'])
        assert label['labels']==r['labels']
        for key in ('longNetPct','shortNetPct'):assert abs(label[key]-r[key])<1e-8
        long,cost_long=trade(m[i+1]['open'],m[i+1:i+17],atr,source['priceTick'],1)
        short,cost_short=trade(m[i+1]['open'],m[i+1:i+17],atr,source['priceTick'],-1)
        assert abs(long-r['longNetPct'])<1e-8 and abs(short-r['shortNetPct'])<1e-8
        volume=statistics.median(b['volume'] for b in d[j-20:j])
        r.update(longStressPct=long-cost_long,shortStressPct=short-cost_short)
        ledger.append({'contract':r['contract'],'signalAt':r['signalAt'],'dailyMedianVolume20':volume,'longStressPct':r['longStressPct'],'shortStressPct':r['shortStressPct']})
        if volume>=10000:qualified.append(r)
    buckets=defaultdict(list)
    for r in qualified:buckets[tuple(r['match'])].append(r)
    for bucket in buckets.values():
        sums={label:sum(r['labels'][label] for r in bucket) for label in bucket[0]['labels']}
        for r in bucket:r['base']={label:(sums[label]-r['labels'][label])/(len(bucket)-1) if len(bucket)>1 else None for label in sums}
    qualified=[r for r in qualified if all(v is not None for v in r['base'].values())]
    patterns=[]
    for original in result['patterns']:
        label=original['target'];path=original['path'];item={**original,'discoveryStatistics':original['statistics']}
        subsets={part:[r for r in qualified if r['partition']==part and matches(r['feature'],path)] for part in PARTS}
        item['statistics']={part:summarize(values,label) for part,values in subsets.items()};item['grade']=grade(item['statistics'])
        direction=-1 if label in ('SHORT_ENTRY','DOWN_MOVE','HIGH_TURN','EXIT_LONG') else 1
        for part,values in subsets.items():
            item['statistics'][part]['meanStressPct']=statistics.mean(r['shortStressPct'] if direction<0 else r['longStressPct'] for r in values) if values else None
        if item.get('withoutChanPath') is not None:
            item['withoutChanStatistics']={part:summarize([r for r in qualified if r['partition']==part and matches(r['feature'],item['withoutChanPath'])],label) for part in PARTS}
            item['chanIncrement']={part:paired([r for r in qualified if r['partition']==part],path,item['withoutChanPath'],label) for part in PARTS}
        patterns.append(item)
    families={family:{'features':len(names),'selectedPatterns':sum(p['family']==family for p in patterns),
                      'improvedPatterns':sum(p['family']==family and p['grade'].startswith(('PROBABILITY_LIFT_SUPPORTED','TENTATIVE_PROBABILITY_LIFT')) for p in patterns)} for family,names in FAMILIES.items()}
    audit={'status':'PASSED','exactLabelsRecomputed':len(rows),'exactNextOpenReturnsRecomputed':2*len(rows),
           'discoveryDecisions':len(rows),'liveEligibleDecisions':len(qualified),'partitions':{part:sum(r['partition']==part for r in qualified) for part in PARTS},
           'roots':len({r['root'] for r in qualified}),'families':families,'patterns':patterns,
           'chanIncrementQualification':'Nested conditions, shared-week bootstrap; adaptive exploratory associations, no causal or fresh independent confirmation.',
           'protocol':registration}
    dump('live-eligibility-audit.json',audit)
    with gzip.open(OUT/'eligibility-cost-ledger.json.gz','wt',encoding='utf-8') as stream:json.dump(ledger,stream,ensure_ascii=False,allow_nan=False)
    model={'version':result['version'],'activeRoots':result['activeRoots'],'labeledDecisions':len(qualified),'discoveryDecisions':len(rows),
           'rawBars':result['rawBars'],'trainingRoots':protocol['trainingRoots'],'heldoutRoots':protocol['heldoutRoots'],
           'universeCodes':[v['root'].split('.')[-1].upper() for v in result['inventory']],
           'families':families,'patterns':patterns,'activityMedianDailyVolume20':10000,
           'qualification':result['dataReuseQualification'],'tradeQualified':False,
           'evidenceSha256':hashlib.sha256((OUT/'live-eligibility-audit.json').read_bytes()).hexdigest()}
    path=ROOT/'config/multifactor-patterns.json'
    if path.exists():raise SystemExit('Frozen model exists; do not overwrite')
    path.write_text(json.dumps(model,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    # Archive the exact sources used, independent of future edits or Git newline filters.
    sources_snapshot={name:(ROOT/name).read_text(encoding='utf-8') for name in protocol['codeHashes']}
    with gzip.open(OUT/'source-snapshot.json.gz','wt',encoding='utf-8') as stream:json.dump(sources_snapshot,stream,ensure_ascii=False)
    print(json.dumps({k:v for k,v in audit.items() if k not in ('patterns','protocol')},ensure_ascii=False))

if __name__=='__main__':main()
