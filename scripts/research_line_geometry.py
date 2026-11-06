"""Registered fixed-rule geometry tests against frozen multi-market outcomes.

Rules are fixed before this run; DEV only selects paths, never later outcomes.
"""
import gzip,hashlib,json,statistics,sys,time
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from backtesting.line_geometry import VERSION,geometry_snapshot
from backtesting.outcome_features import matches
from discover_outcome_patterns import summarize
from research_multifactor_chan import grade

OUT=ROOT/'docs/research/data/line-geometry-2026-11-07'
OLD=ROOT/'docs/research/data/multifactor-chan-2026-11-07'
SOURCE=ROOT/'data/history/intraday-active-study'
PARTS=('DEV','TIME','ASSET','RECENT')
FAMILY_LABELS={'GEOMETRY':'仅线形','GEOMETRY_INDICATORS':'线形与量能','GEOMETRY_CHAN':'线形与缠论','GEOMETRY_BOTH':'线形与量能及缠论'}

def condition(feature,operator,threshold):return {'feature':feature,'operator':operator,'threshold':threshold}
def flag(name):return condition('line.'+name,'GT',.5)

EVENTS=(
 ('CHANNEL_UP','上破旧回归通道上轨',1,[flag('channelUpperCrossUp')],('LONG_ENTRY','UP_MOVE','EXIT_SHORT')),
 ('CHANNEL_DOWN','下破旧回归通道下轨',-1,[flag('channelLowerCrossDown')],('SHORT_ENTRY','DOWN_MOVE','EXIT_LONG')),
 ('CHANNEL_RECOVER','下轨外收回旧通道',1,[flag('channelLowerCrossUp')],('LONG_ENTRY','LOW_TURN','EXIT_SHORT')),
 ('CHANNEL_REJECT','上轨外跌回旧通道',-1,[flag('channelUpperCrossDown')],('SHORT_ENTRY','HIGH_TURN','EXIT_LONG')),
 ('RESISTANCE_UP','上破已确认高点阻力斜线',1,[flag('resistanceKnown'),flag('resistanceCrossUp')],('LONG_ENTRY','UP_MOVE')),
 ('SUPPORT_DOWN','下破已确认低点支撑斜线',-1,[flag('supportKnown'),flag('supportCrossDown')],('SHORT_ENTRY','DOWN_MOVE')),
 ('RANGE_UP','突破此前20柱高点',1,[flag('rangeHighCrossUp')],('LONG_ENTRY','UP_MOVE')),
 ('RANGE_DOWN','跌破此前20柱低点',-1,[flag('rangeLowCrossDown')],('SHORT_ENTRY','DOWN_MOVE')),
 ('UP_CHANNEL_RETEST','上斜通道接近下轨',1,[condition('line.slopeATR','GT',0),condition('line.channelLowerDistanceATR','GT',-.3),condition('line.channelLowerDistanceATR','LE',.3)],('LONG_ENTRY','LOW_TURN')),
 ('DOWN_CHANNEL_RETEST','下斜通道接近上轨',-1,[condition('line.slopeATR','LE',0),condition('line.channelUpperDistanceATR','GT',-.3),condition('line.channelUpperDistanceATR','LE',.3)],('SHORT_ENTRY','HIGH_TURN')),
)

TARGET_LABELS={'LONG_ENTRY':'多头入场窗口','SHORT_ENTRY':'空头入场窗口','UP_MOVE':'后续上行','DOWN_MOVE':'后续下行',
               'LOW_TURN':'向上转折','HIGH_TURN':'向下转折','EXIT_LONG':'多头回撤风险','EXIT_SHORT':'空头反弹风险'}

def candidates():
    values=[]
    for event,label,direction,path,targets in EVENTS:
        # Identical fixed additions for every event; no per-pattern tuning.
        volume=[condition('m15.volumeRatio20','GT',1.2)]
        chan=[condition('m15.zoneKnown','GT',.5),condition('m15.zonePositionATR','LE' if direction>0 else 'GT',0)]
        for family,extra in (('GEOMETRY',[]),('GEOMETRY_INDICATORS',volume),('GEOMETRY_CHAN',chan),('GEOMETRY_BOTH',volume+chan)):
            for target in targets:
                values.append({'id':f'{event}_{family}_{target}','family':family,'target':target,
                               'label':label+' · '+TARGET_LABELS[target], 'path':[*path,*extra],
                               'containsChan':'CHAN' in family or family=='GEOMETRY_BOTH','tradeQualified':False})
    return values

def dump(name,value):(OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/'protocol.json').exists() or (ROOT/'config/line-patterns.json').exists():raise SystemExit('Registered geometry study/model already exists; do not overwrite')
    fixed=candidates()
    protocol={'version':VERSION,'registeredAt':time.time(),'method':'Fixed candidate rules from previously known price-geometry definitions; outcome-first target comparison, not adaptive threshold fitting.',
              'data':'Reuse the same 34 currently-active actual contracts and previously studied historical decision labels; not a fresh independent holdout.',
              'geometry':'Evaluate latest closed bar against lines fitted on earlier bars only. 60 closes OLS center +/-2 population residual SD; previous20 high/low; last two strict 2-left/2-right confirmed pivot extrema at least5 bars apart from prior120. Current/evolving bars excluded from fit.',
              'partitions':'Existing DEV before July 2026 on26 roots; TIME July-Sept same roots; ASSET July-Sept other8 roots; RECENT Oct+ all roots. Inherited labels purge forward16-bar boundary crossings.',
              'eligibility':'Same frozen600-15m/65-daily context, volume current15m>=100, preceding20 complete daily median volume>=10000; retained frozen common rows only.',
              'unavailableGeometryPolicy':'After preserved attempt1 stopped on a real zero priorATR, uniformly exclude WARMING/INVALID geometry before every group/control comparison. Record every exclusion. No exclusion uses future labels or returns.',
              'selection':'DEV only: >=100 samples, >=8 roots, >=20 positive labels, probability lift>=1 percentage point over root/month/hour/partition matched controls; up to2 per target/family by DEV lift then samples. No thresholds or selection changes from TIME/ASSET/RECENT.',
              'statistics':'500 joint-week block bootstrap; >=8 weeks for intervals. Overlapping events, current-active universe and repeated historical research remain limitations; no multiple-testing confirmation.',
              'costs':'Reuse independently audited next-open1ATR stop/2ATR target/max16bar returns,1bp and1tick per side; stress doubles both; EXIT labels use opposite-direction observation trades, not a liquidation-policy test.',
              'candidateCount':len(fixed),'candidates':fixed,
              'codeHashes':{p.as_posix():hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in (Path('backtesting/line_geometry.py'),Path('scripts/research_line_geometry.py'))},
              'inputHashes':{name:hashlib.sha256((OLD/name).read_bytes()).hexdigest() for name in ('decisions.json.gz','eligibility-cost-ledger.json.gz','results.json')}}
    dump('protocol.json',protocol)
    with gzip.open(OLD/'decisions.json.gz','rt',encoding='utf-8') as stream:old_rows=json.load(stream)
    with gzip.open(OLD/'eligibility-cost-ledger.json.gz','rt',encoding='utf-8') as stream:ledger=json.load(stream)
    costs={(r['contract'],r['signalAt']):r for r in ledger};previous=json.loads((OLD/'results.json').read_text(encoding='utf-8'))
    sources={};indices={};inventory=[]
    for item in previous['inventory']:
        file=SOURCE/item['file'];raw=file.read_bytes();assert hashlib.sha256(raw).hexdigest()==item['sha256']
        source=json.loads(raw);sources[source['contract']]=source
        indices[source['contract']]={b['timestamp']:i for i,b in enumerate(source['bars15m'])}
        inventory.append({k:item[k] for k in ('root','contract','file','sha256','rawBars','usableBars')})
    rows=[];needed={'m15.volumeRatio20','m15.zoneKnown','m15.zonePositionATR'};parity=[];excluded=[]
    for old in old_rows:
        cost=costs[(old['contract'],old['signalAt'])]
        if cost['dailyMedianVolume20']<10000:continue
        source=sources[old['contract']];i=indices[old['contract']][old['signalAt']];m=source['bars15m']
        snapshot=geometry_snapshot(m[i-120:i+1],False)
        if snapshot['status']!='READY':
            excluded.append({'contract':old['contract'],'signalAt':old['signalAt'],'partition':old['partition'],
                             'status':snapshot['status'],'reason':snapshot['message']});continue
        values={**{key:old['feature'][key] for key in needed},**snapshot['features']}
        row={key:old[key] for key in ('root','contract','partition','signalAt','confirmedAt','week','match','labels','longNetPct','shortNetPct')}
        row.update(feature=values,longStressPct=cost['longStressPct'],shortStressPct=cost['shortStressPct'])
        rows.append(row)
        # Check the same numerical geometry in the 600-closed live context, across all roots.
        if not any(p['contract']==old['contract'] for p in parity):
            live=geometry_snapshot(m[i-599:i+1],False)
            assert snapshot['features']==live['features']
            parity.append({'contract':old['contract'],'signalAt':old['signalAt'],'featuresMatched':True})
    buckets=defaultdict(list)
    for row in rows:buckets[tuple(row['match'])].append(row)
    for bucket in buckets.values():
        sums={label:sum(row['labels'][label] for row in bucket) for label in TARGET_LABELS}
        for row in bucket:row['base']={label:(sums[label]-row['labels'][label])/(len(bucket)-1) if len(bucket)>1 else None for label in sums}
    rows=[row for row in rows if all(v is not None for v in row['base'].values())]
    assert len({r['root'] for r in rows})>=16
    all_candidates=[]
    for candidate in fixed:
        subsets={part:[r for r in rows if r['partition']==part and matches(r['feature'],candidate['path'])] for part in PARTS}
        stats={part:summarize(values,candidate['target']) for part,values in subsets.items()}
        direction=-1 if candidate['target'] in ('SHORT_ENTRY','DOWN_MOVE','HIGH_TURN','EXIT_LONG') else 1
        for part,values in subsets.items():
            stats[part]['meanStressPct']=statistics.mean(r['shortStressPct'] if direction<0 else r['longStressPct'] for r in values) if values else None
        train=stats['DEV'];reasons=[]
        if train['samples']<100:reasons.append('DEV_SAMPLES_BELOW_100')
        if train['roots']<8:reasons.append('DEV_ROOTS_BELOW_8')
        if train.get('positiveLabels',0)<20:reasons.append('DEV_POSITIVES_BELOW_20')
        if train['liftPp'] is None or train['liftPp']<1:reasons.append('DEV_LIFT_BELOW_1PP')
        all_candidates.append({**candidate,'statistics':stats,'grade':grade(stats),'trainingRejectionReasons':reasons,'selected':False})
    for family in FAMILY_LABELS:
        for target in TARGET_LABELS:
            eligible=[p for p in all_candidates if p['family']==family and p['target']==target and not p['trainingRejectionReasons']]
            for p in sorted(eligible,key=lambda p:(-p['statistics']['DEV']['liftPp'],-p['statistics']['DEV']['samples']))[:2]:p['selected']=True
    selected=[p for p in all_candidates if p['selected']]
    result={'version':VERSION,'activeRoots':len({r['root'] for r in rows}),'labeledDecisions':len(rows),
            'partitions':{part:sum(r['partition']==part for r in rows) for part in PARTS},'candidateCount':len(fixed),
            'allCandidates':all_candidates,'patterns':selected,'inventory':inventory,'featureNames':sorted({k for r in rows for k in r['feature']}),
            'offlineLiveParityChecks':parity,'geometryExclusions':excluded,'qualification':protocol['data'],
            'families':{key:{'label':label,'candidates':sum(p['family']==key for p in all_candidates),
                             'selectedPatterns':sum(p['family']==key for p in selected),
                             'improvedPatterns':sum(p['family']==key and p['grade'].startswith(('PROBABILITY_LIFT_SUPPORTED','TENTATIVE_PROBABILITY_LIFT')) for p in selected)} for key,label in FAMILY_LABELS.items()}}
    dump('results.json',result)
    with gzip.open(OUT/'decisions.json.gz','wt',encoding='utf-8') as stream:json.dump(rows,stream,ensure_ascii=False,allow_nan=False)
    dump('source-snapshot.json',{key:(ROOT/key).read_text(encoding='utf-8') for key in protocol['codeHashes']})
    old_protocol=json.loads((OLD/'protocol.json').read_text(encoding='utf-8'))
    feature_labels={'line.slopeATR':'前60柱回归斜率/ATR','line.widthATR':'前60柱回归通道宽度/ATR','line.fitR2':'回归拟合R²',
                    'line.supportKnown':'存在两确认低点支撑斜线','line.resistanceKnown':'存在两确认高点阻力斜线',
                    'line.channelUpperCrossUp':'收盘上破此前拟合的通道上轨','line.channelUpperCrossDown':'收盘从上轨外回到通道',
                    'line.channelLowerCrossUp':'收盘从下轨外收回通道','line.channelLowerCrossDown':'收盘下破此前拟合的通道下轨',
                    'line.resistanceCrossUp':'收盘上破已确认阻力斜线','line.supportCrossDown':'收盘下破已确认支撑斜线',
                    'line.rangeHighCrossUp':'收盘突破此前20柱高点','line.rangeLowCrossDown':'收盘跌破此前20柱低点',
                    'line.channelUpperDistanceATR':'收盘距旧通道上轨/ATR','line.channelLowerDistanceATR':'收盘距旧通道下轨/ATR',
                    'm15.volumeRatio20':'15分钟柱量/此前20柱均量','m15.zoneKnown':'存在已确认三笔中枢',
                    'm15.zonePositionATR':'价格距最近中枢边界/ATR（中枢内或未知为0）'}
    model={'version':VERSION,'activeRoots':result['activeRoots'],'labeledDecisions':len(rows),'partitions':result['partitions'],
           'universeCodes':[v['root'].split('.')[-1].upper() for v in inventory],
           'trainingRoots':old_protocol['trainingRoots'],'heldoutRoots':old_protocol['heldoutRoots'],
           'patterns':selected,'allCandidates':all_candidates,'candidateCount':len(fixed),'families':result['families'],
           'featureLabels':feature_labels,'qualification':protocol['data'],'tradeQualified':False,
           'activityMedianDailyVolume20':10000,'evidenceSha256':hashlib.sha256((OUT/'results.json').read_bytes()).hexdigest()}
    (ROOT/'config/line-patterns.json').write_text(json.dumps(model,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    dump('manifest.json',[{'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
                          for p in sorted(OUT.iterdir()) if p.is_file() and p.name not in ('manifest.json','chart-examples.json')])
    print(json.dumps({k:result[k] for k in ('version','activeRoots','labeledDecisions','partitions','candidateCount','families')},ensure_ascii=False))

if __name__=='__main__':main()
