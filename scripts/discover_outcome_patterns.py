"""Outcome-first reverse analysis across active markets; chronological and held-out assets."""
import bisect,gzip,hashlib,json,math,random,statistics,sys
from collections import defaultdict
from datetime import datetime,timedelta,timezone
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtesting.outcome_features import NAMES,LABELS,vector,targets,matches
SOURCE=ROOT/'data/history/intraday-active-study';OUT=ROOT/'docs/research/data/outcome-discovery-2026-11-07';SH=timezone(timedelta(hours=8))
def dt(s):return datetime.fromisoformat(s.replace('Z','+00:00'))
def dump(name,value):(OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def trees(x,y,indices,path=(),depth=0):
    if depth>=3 or len(indices)<800:return [(indices,list(path))]
    probability=float(y[indices].mean());parent=probability*(1-probability);best=None
    for j,name in enumerate(NAMES):
        values=x[indices,j]
        for threshold in sorted(set(np.quantile(values,[.2,.4,.6,.8]).tolist())):
            mask=values<=threshold;left=indices[mask];right=indices[~mask]
            if len(left)<400 or len(right)<400:continue
            a=float(y[left].mean());b=float(y[right].mean())
            score=parent-(len(left)*a*(1-a)+len(right)*b*(1-b))/len(indices)
            if best is None or score>best[0]:best=(score,name,float(threshold),left,right)
    if best is None or best[0]<=1e-6:return [(indices,list(path))]
    _,name,t,left,right=best
    return trees(x,y,left,(*path,{'feature':name,'operator':'LE','threshold':t}),depth+1)+trees(x,y,right,(*path,{'feature':name,'operator':'GT','threshold':t}),depth+1)
def summarize(rows,label,seed=7):
    if not rows:return {'samples':0,'roots':0,'probability':None,'matchedBaseProbability':None,'liftPp':None,'probabilityInterval':None,'liftIntervalPp':None,'meanNetPct':None}
    blocks=defaultdict(list)
    for r in rows:blocks[r['week']].append(r)
    n=len(rows);p=sum(r['labels'][label] for r in rows)/n;baseline=statistics.mean(r['base'][label] for r in rows)
    direction=-1 if label in ('SHORT_ENTRY','DOWN_MOVE','HIGH_TURN','EXIT_LONG') else 1
    values=[r['shortNetPct'] if direction<0 else r['longNetPct'] for r in rows]
    ci=None;delta_ci=None
    if len(blocks)>=8:
        aggregate=[(len(v),sum(r['labels'][label] for r in v),sum(r['base'][label] for r in v)) for v in blocks.values()]
        rng=random.Random(seed);ps=[];ds=[]
        for _ in range(500):
            chosen=[aggregate[rng.randrange(len(aggregate))] for _ in aggregate];total=sum(v[0] for v in chosen)
            a=sum(v[1] for v in chosen)/total;b=sum(v[2] for v in chosen)/total;ps.append(a);ds.append((a-b)*100)
        ps.sort();ds.sort();ci=[ps[12],ps[487]];delta_ci=[ds[12],ds[487]]
    return {'samples':n,'roots':len({r['root'] for r in rows}),'weeks':len(blocks),'positiveLabels':sum(r['labels'][label] for r in rows),
        'probability':p,'matchedBaseProbability':baseline,'liftPp':(p-baseline)*100,'probabilityInterval':ci,'liftIntervalPp':delta_ci,
        'meanNetPct':statistics.mean(values),'costPositiveFraction':sum(v>0 for v in values)/n,
        'pnlScope':'1ATR stop/2ATR target/max16 bars; EXIT labels show opposite-side observation returns, not a tested liquidation policy'}
def main():
    OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/'results.json').exists():raise SystemExit('Completed outcome experiment exists; never overwrite.')
    collection=json.loads((SOURCE/'collection.json').read_text(encoding='utf-8'));items=[r for r in collection['results'] if r['status']=='COLLECTED']
    if len(items)<16:raise ValueError('At least sixteen active roots required')
    roots=sorted([r['root'] for r in items],key=lambda s:hashlib.sha256(s.encode()).hexdigest());holdout=set(roots[:8]);training=set(roots[8:])
    protocol={'version':'outcome-first-v1','universe':'34 candidates; actual main contract median preceding 20 completed daily volumes >=10000; current active universe bias disclosed.',
        'method':'First label realized future moves, tradable barriers, turns and adverse paths; then reverse-discover past-feature conditions.',
        'labels':LABELS,'featureNames':NAMES,'futureWindow':16,'tree':{'depth':3,'minLeaf':400,'thresholds':'training-only 20/40/60/80 percentiles','maxPatternsPerLabel':2},
        'patternSelection':'Training probability at least base+3pp, positive labels>=30, roots>=12; maximum two per target by training probability lift.',
        'partition':'Training roots before July 2026; same roots July-Sept time-validation; held-out roots July-Sept asset-validation; all roots October onward recent comparison.',
        'trainingRoots':sorted(training),'heldoutRoots':sorted(holdout),'activityMedianThreshold':10000,
        'outcomeDefinition':'Entry next 15-minute open. LONG/SHORT: +2 prior ATR before -1 ATR within 16 bars, positive after 1bp/side+1 tick/side; ambiguous bar loses. UP/DOWN: eight-bar close >1 ATR. Turns: four bars each side plus 8-bar 1ATR reversal. Exit-risk: 8-bar adverse excursion>=1.5ATR and terminal adverse>=.5ATR.',
        'controls':'All eligible decisions matched by root/month/hour/partition, excluding the event itself; not a randomized causal experiment.',
        'interval':'500 week-block bootstrap draws shared across markets; 95% percentile intervals only with >=8 weeks, not independent tick trials.',
        'qualification':'Historical conditional probabilities, not 100% success or calibrated live probabilities. Overlapping forward labels and current-active universe limit generalization.',
        'codeHashes':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),ROOT/'backtesting/outcome_features.py']}}
    dump('protocol.json',protocol);rows=[];inventory=[]
    for item in items:
        file=SOURCE/item['file'];raw=file.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=item['sha256']:raise ValueError('Changed input')
        data=json.loads(raw);m=data['bars15m'];d=data['barsDaily'];old=len(m)
        gaps=[i for i in range(1,len(d)) if dt(d[i]['timestamp'])-dt(d[i-1]['timestamp'])>timedelta(days=365)]
        if gaps:
            cutoff=dt(d[gaps[-1]]['timestamp']);d=d[gaps[-1]:];m=[b for b in m if dt(b['timestamp'])>=cutoff]
        inventory.append({**item,'usableBars':len(m),'lifecycleRejected':old-len(m)});times=[dt(b['timestamp']).timestamp() for b in d]
        for i in range(119,len(m)-17):
            bar=m[i];confirmation=m[i+1];day=dt(confirmation['timestamp']).astimezone(SH).date().isoformat();root=item['root']
            partition='DEV' if day<'2026-07-01' and root in training else 'TIME' if day<'2026-10-01' and day>='2026-07-01' and root in training else 'ASSET' if '2026-07-01'<=day<'2026-10-01' and root in holdout else 'RECENT' if day>='2026-10-01' else None
            if partition is None or bar['volume']<100:continue
            j=bisect.bisect_right(times,dt(confirmation['timestamp']).timestamp())-1
            if j<25 or dt(bar['timestamp']).timestamp()<times[j]:continue
            future=m[i+1:i+17]
            if any(b['volume']<=0 for b in future):continue
            end=dt(future[-1]['timestamp']).astimezone(SH).date().isoformat()
            if partition=='DEV' and end>='2026-07-01' or partition in ('TIME','ASSET') and end>='2026-10-01':continue
            feature=vector(m[i-119:i+1],d[:j])
            if feature is None:continue
            outcome=targets(bar,m[:i],future,feature['atr'],data['priceTick'])
            stamp=dt(bar['timestamp']).astimezone(SH);week=stamp.isocalendar()
            rows.append({'root':root,'contract':data['contract'],'partition':partition,'signalAt':bar['timestamp'],'confirmedAt':confirmation['timestamp'],
                'dailyReferenceAt':d[j-1]['timestamp'],'formingDayAt':d[j]['timestamp'],'feature':feature['values'],
                'week':f'{week.year}-{week.week}','match':(root,partition,stamp.strftime('%Y-%m'),stamp.hour),**outcome})
    # Baselines are evaluated inside each partition; no later labels enter training baselines.
    buckets=defaultdict(list)
    for r in rows:buckets[r['match']].append(r)
    for bucket in buckets.values():
        sums={label:sum(r['labels'][label] for r in bucket) for label in LABELS}
        for r in bucket:r['base']={label:(sums[label]-r['labels'][label])/(len(bucket)-1) if len(bucket)>1 else None for label in LABELS}
    rows=[r for r in rows if all(v is not None for v in r['base'].values())]
    x=np.array([[r['feature'][name] for name in NAMES] for r in rows],dtype=float);indices=np.array([i for i,r in enumerate(rows) if r['partition']=='DEV']);patterns=[]
    if len(indices)<4000:raise ValueError('Insufficient development observations')
    for label in LABELS:
        y=np.array([r['labels'][label] for r in rows],dtype=float);base=float(y[indices].mean());leaves=trees(x,y,indices);candidates=[]
        for leaf,path in leaves:
            p=float(y[leaf].mean());coverage=len({rows[int(i)]['root'] for i in leaf});positives=int(y[leaf].sum())
            if p>=base+.03 and positives>=30 and coverage>=12:candidates.append((p-base,len(leaf),path))
        for rank,(_,_,path) in enumerate(sorted(candidates,key=lambda v:(-v[0],-v[1]))[:2]):
            subsets={part:[r for r in rows if r['partition']==part and matches(r['feature'],path)] for part in ('DEV','TIME','ASSET','RECENT')}
            stats={part:summarize(v,label) for part,v in subsets.items()};time_s=stats['TIME'];asset_s=stats['ASSET'];recent=stats['RECENT']
            adequate=time_s['samples']>=100 and asset_s['samples']>=100 and time_s['roots']>=8 and asset_s['roots']>=4
            lift=adequate and time_s['liftPp']>0 and asset_s['liftPp']>0
            supported=lift and time_s['liftIntervalPp'] is not None and asset_s['liftIntervalPp'] is not None and time_s['liftIntervalPp'][0]>0 and asset_s['liftIntervalPp'][0]>0
            grade='PROBABILITY_LIFT_SUPPORTED' if supported else 'TENTATIVE_PROBABILITY_LIFT' if lift else 'INSUFFICIENT' if not adequate else 'TIME_OR_ASSET_DEPENDENT'
            if recent['samples']>=100 and recent['liftPp']<0:grade+='__RECENT_WEAKENING'
            patterns.append({'id':label+'_'+str(rank+1),'target':label,'label':LABELS[label],'path':path,'statistics':stats,'grade':grade,'tradeQualified':False})
    report={'version':protocol['version'],'status':'HISTORICAL_PROBABILITY_REFERENCE','data':inventory,'activeRoots':len(items),'rawBars':sum(r['bars15m'] for r in inventory),
        'usableBars':sum(r['usableBars'] for r in inventory),'labeledDecisions':len(rows),'partitions':{p:sum(r['partition']==p for r in rows) for p in ('DEV','TIME','ASSET','RECENT')},
        'baseRates':{p:summarize([r for r in rows if r['partition']==p],'LONG_ENTRY') for p in ('DEV','TIME','ASSET','RECENT')},
        'patterns':patterns,'trainingRoots':sorted(training),'heldoutRoots':sorted(holdout),'qualification':protocol['qualification']}
    dump('results.json',report)
    with gzip.open(OUT/'labeled-decisions.json.gz','wt',encoding='utf-8') as stream:json.dump(rows,stream,ensure_ascii=False,allow_nan=False)
    print(json.dumps({'activeRoots':len(items),'rawBars':report['rawBars'],'usableBars':report['usableBars'],'labeled':len(rows),'partitions':report['partitions'],
        'patterns':[{'id':p['id'],'grade':p['grade'],'TIME':p['statistics']['TIME']['probability'],'ASSET':p['statistics']['ASSET']['probability'],'recent':p['statistics']['RECENT']['probability']} for p in patterns]},ensure_ascii=True),flush=True)
if __name__=='__main__':main()
