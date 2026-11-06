"""Registered, outcome-first multi-period/Chan ablation on frozen real-market data."""
import bisect,gzip,hashlib,json,random,statistics,sys,time
from collections import defaultdict
from datetime import timedelta
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from backtesting.multifactor_features import VERSION_ID,NAMES,FAMILIES,CHAN_NAMES,WINDOW,aggregate,context,combine,extended_vector,stamp
from backtesting.outcome_features import LABELS,matches
from discover_outcome_patterns import summarize,dt

SOURCE=ROOT/'data/history/intraday-active-study'
PREVIOUS=ROOT/'docs/research/data/outcome-discovery-2026-11-07'
OUT=ROOT/'docs/research/data/multifactor-chan-2026-11-07'
PARTS=('DEV','TIME','ASSET','RECENT')

def dump(name,obj):
    (OUT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')

def tree(x,y,indices,names,audit,path=(),depth=0):
    if depth>=3 or len(indices)<800:return [(indices,list(path))]
    p=float(y[indices].mean()); impurity=p*(1-p);best=None;tested=0;comparisons=[]
    for j,name in enumerate(names):
        values=x[indices,j]
        for threshold in sorted(set(np.quantile(values,[.2,.4,.6,.8]).tolist())):
            tested+=1;mask=values<=threshold;left=indices[mask];right=indices[~mask]
            comparison={'feature':name,'threshold':float(threshold),'leftSamples':len(left),'rightSamples':len(right)}
            comparisons.append(comparison)
            if len(left)<400 or len(right)<400:
                comparison['rejected']='MINIMUM_LEAF';continue
            a=float(y[left].mean());b=float(y[right].mean())
            gain=impurity-(len(left)*a*(1-a)+len(right)*b*(1-b))/len(indices)
            comparison.update(gain=gain,leftProbability=a,rightProbability=b)
            if best is None or gain>best[0]:best=(gain,name,float(threshold),left,right)
    record={'path':list(path),'samples':len(indices),'testedSplits':tested,'candidateSplits':comparisons}
    if best is not None:record['best']={'gain':best[0],'feature':best[1],'threshold':best[2]}
    audit.append(record)
    if best is None or best[0]<=1e-6:return [(indices,list(path))]
    _,name,threshold,left,right=best
    return (tree(x,y,left,names,audit,(*path,{'feature':name,'operator':'LE','threshold':threshold}),depth+1)
            +tree(x,y,right,names,audit,(*path,{'feature':name,'operator':'GT','threshold':threshold}),depth+1))

def grade(stats):
    a,b=stats['TIME'],stats['ASSET']
    adequate=a['samples']>=100 and b['samples']>=100 and a['roots']>=8 and b['roots']>=4
    improved=adequate and a['liftPp']>0 and b['liftPp']>0
    supported=improved and all(s['liftIntervalPp'] and s['liftIntervalPp'][0]>0 for s in (a,b))
    value='PROBABILITY_LIFT_SUPPORTED' if supported else 'TENTATIVE_PROBABILITY_LIFT' if improved else 'INSUFFICIENT' if not adequate else 'TIME_OR_ASSET_DEPENDENT'
    if stats['RECENT']['samples']>=100 and stats['RECENT']['liftPp']<0:value+='__RECENT_WEAKENING'
    return value

def build_rows():
    with gzip.open(PREVIOUS/'labeled-decisions.json.gz','rt',encoding='utf-8') as stream:original=json.load(stream)
    lookup={(r['contract'],r['signalAt']):r for r in original}
    collection=json.loads((SOURCE/'collection.json').read_text(encoding='utf-8'))
    rows=[];inventory=[];parity=[]
    for number,item in enumerate(collection['results']):
        if item['status']!='COLLECTED':continue
        path=SOURCE/item['file'];raw=path.read_bytes();assert hashlib.sha256(raw).hexdigest()==item['sha256']
        source=json.loads(raw);m=source['bars15m'];d=source['barsDaily'];raw_count=len(m)
        gaps=[i for i in range(1,len(d)) if dt(d[i]['timestamp'])-dt(d[i-1]['timestamp'])>timedelta(days=365)]
        if gaps:
            cutoff=stamp(d[gaps[-1]]['timestamp']);d=d[gaps[-1]:];m=[b for b in m if stamp(b['timestamp'])>=cutoff]
        daily_times=[stamp(b['timestamp']) for b in d];minute_times=[stamp(b['timestamp']) for b in m]
        larger={period:aggregate(m,period) for period in (30,60)}
        times={period:[b['availableAt'] for b in bars] for period,bars in larger.items()}
        starts={period:[stamp(b['timestamp']) for b in bars] for period,bars in larger.items()}
        cache={30:{},60:{}};accepted=0;root_parity=0
        for i in range(WINDOW-1,len(m)-17):
            prior=lookup.get((source['contract'],m[i]['timestamp']))
            if prior is None:continue
            j=bisect.bisect_right(daily_times,minute_times[i+1])-1
            if j<65:continue
            minutes=m[i-WINDOW+1:i+1];contexts={'m15':context(minutes[-120:])};counts={'m15':120}
            for period,bars in larger.items():
                hi=bisect.bisect_right(times[period],minute_times[i]+900)
                lo=max(hi-120,bisect.bisect_left(starts[period],minute_times[i-WINDOW+1]))
                key=(lo,hi)
                if key not in cache[period]:cache[period][key]=context(bars[lo:hi])
                contexts[f'm{period}']=cache[period][key];counts[f'm{period}']=hi-lo
            features=combine(minutes,d[:j],contexts,counts)
            if features is None:continue
            assert set(features['values'])==set(NAMES)
            if root_parity<3 and accepted%73==0:
                expected=extended_vector(minutes,d[:j]);assert expected==features
                parity.append({'contract':source['contract'],'signalAt':m[i]['timestamp'],'matched':True});root_parity+=1
            rows.append({**prior,'feature':features['values'],'contextBars':features['contextBars']})
            accepted+=1
        inventory.append({**item,'rawBars':raw_count,'usableBars':len(m),'commonDecisions':accepted})
        print(json.dumps({'stage':'FEATURES','root':item['root'],'decisions':accepted,'done':number+1}),flush=True)
    # Recompute controls on exactly the common eligible sample for fair ablation.
    buckets=defaultdict(list)
    for r in rows:buckets[tuple(r['match'])].append(r)
    for bucket in buckets.values():
        sums={label:sum(r['labels'][label] for r in bucket) for label in LABELS}
        for r in bucket:r['base']={label:(sums[label]-r['labels'][label])/(len(bucket)-1) if len(bucket)>1 else None for label in LABELS}
    rows=[r for r in rows if all(v is not None for v in r['base'].values())]
    return rows,inventory,parity

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/'protocol.json').exists():raise SystemExit('Registered experiment exists. Use a new version/directory; do not overwrite.')
    previous=json.loads((PREVIOUS/'protocol.json').read_text(encoding='utf-8'))
    protocol={'version':VERSION_ID,'registeredAt':time.time(),'source':'Frozen 34 actual active contracts; same historical dataset as v1; no fresh independent holdout claim.',
              'trainingRoots':previous['trainingRoots'],'heldoutRoots':previous['heldoutRoots'],
              'partitions':previous['partition'],'labelDefinitions':previous['outcomeDefinition'],
              'families':FAMILIES,'featureNames':NAMES,'window':WINDOW,
              'aggregation':'Complete Shanghai clock 30/60 minute buckets from 15m, no partial or gapped buckets; common 15m decisions; 65 completed daily bars.',
              'chan':'aiquant-chan-v1 rolling <=120 bars per period. Confirmed pens/segments/fractals, fixed three-pen zones, active B1/S1/B2/S2/B3/S3 research candidates. Provisional tails excluded; confirmation age is explicit.',
              'search':{'depth':3,'minimumLeaf':400,'quantiles':[.2,.4,.6,.8],'minimumTrainingLiftPp':3,'minimumPositiveLabels':30,'minimumRoots':12,'maxPerTargetPerFamily':2},
              'controls':'Same common observations/root/month/hour/partition, excluding self. Chan conditional ablation removes Chan terms from each combined path without refitting.',
              'selection':'Only DEV selects splits and ranks paths. TIME/ASSET/RECENT report results and evidence grades, never alter fitted splits.',
              'multipleTesting':'Exploratory adaptive search over correlated features. Week bootstrap intervals do not adjust for all searches; no confirmatory discovery or profitability claim.',
              'codeHashes':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),ROOT/'backtesting/multifactor_features.py',ROOT/'chanlun_worker/native.py']}}
    dump('protocol.json',protocol)  # Written before computing any new outcomes/paths.
    rows,inventory,parity=build_rows()
    assert len(inventory)>=16 and len({r['root'] for r in rows})>=16
    train=np.array([i for i,r in enumerate(rows) if r['partition']=='DEV']);patterns=[];audits={};leaves_audit=[]
    assert len(train)>=4000
    for family,names in FAMILIES.items():
        x=np.array([[r['feature'][name] for name in names] for r in rows],dtype=float)
        for label in LABELS:
            y=np.array([r['labels'][label] for r in rows]);base=float(y[train].mean());nodes=[]
            leaves=tree(x,y,train,names,nodes);candidates=[]
            for indices,path in leaves:
                p=float(y[indices].mean());positive=int(y[indices].sum());roots=len({rows[int(i)]['root'] for i in indices})
                reasons=[]
                if p<base+.03:reasons.append('LIFT_BELOW_3PP')
                if positive<30:reasons.append('POSITIVE_LABELS_BELOW_30')
                if roots<12:reasons.append('ROOTS_BELOW_12')
                record={'family':family,'target':label,'path':path,'trainingSamples':len(indices),'positiveLabels':positive,'roots':roots,'probability':p,'base':base,'rejected':reasons,'selected':False}
                leaves_audit.append(record)
                if not reasons:candidates.append((p-base,len(indices),path,record))
            for rank,(_,_,path,record) in enumerate(sorted(candidates,key=lambda v:(-v[0],-v[1]))[:2]):
                record['selected']=True
                subsets={part:[r for r in rows if r['partition']==part and matches(r['feature'],path)] for part in PARTS}
                stats={part:summarize(values,label) for part,values in subsets.items()}
                item={'id':family+'_'+label+'_'+str(rank+1),'family':family,'target':label,'label':LABELS[label],
                      'path':path,'statistics':stats,'grade':grade(stats),'tradeQualified':False,
                      'containsChan':any(r['feature'].split('.')[-1] in CHAN_NAMES for r in path)}
                if family=='COMBINED' and item['containsChan']:
                    technical_path=[r for r in path if r['feature'].split('.')[-1] not in CHAN_NAMES]
                    item['withoutChanPath']=technical_path
                    item['withoutChanStatistics']={part:summarize([r for r in rows if r['partition']==part and matches(r['feature'],technical_path)],label) for part in PARTS}
                patterns.append(item)
            audits[family+':'+label]=nodes
            print(json.dumps({'stage':'SEARCH','family':family,'target':label,'leaves':len(leaves),'eligible':len(candidates)}),flush=True)
    result={'version':VERSION_ID,'activeRoots':len(inventory),'labeledDecisions':len(rows),'rawBars':sum(v['rawBars'] for v in inventory),
            'partitions':{part:sum(r['partition']==part for r in rows) for part in PARTS},'inventory':inventory,'patterns':patterns,
            'families':{family:{'features':len(names),'selectedPatterns':sum(p['family']==family for p in patterns),
                                 'improvedPatterns':sum(p['family']==family and p['grade'].startswith(('PROBABILITY_LIFT_SUPPORTED','TENTATIVE_PROBABILITY_LIFT')) for p in patterns)} for family,names in FAMILIES.items()},
            'nativeCandidateFrequency':{period:{name:sum(r['feature'][period+'.'+name]>0 for r in rows) for name in ('B1','S1','B2','S2','B3','S3')} for period in ('m15','m30','m60')},
            'offlineLiveParityChecks':len(parity),'dataReuseQualification':protocol['source']}
    with gzip.open(OUT/'decisions.json.gz','wt',encoding='utf-8') as stream:json.dump(rows,stream,ensure_ascii=False,allow_nan=False)
    dump('candidate-audit.json',{'nodes':audits,'leaves':leaves_audit,'parity':parity});dump('results.json',result)
    print(json.dumps({'stage':'COMPLETE',**{k:v for k,v in result.items() if k in ('activeRoots','labeledDecisions','partitions','families','nativeCandidateFrequency')}}),flush=True)

if __name__=='__main__':main()
