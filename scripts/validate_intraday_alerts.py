"""Frozen 15-minute validation; daily references known at successor confirmation only."""
import bisect,gzip,hashlib,json,statistics,sys
from collections import defaultdict
from datetime import datetime,timedelta,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'docs/research/data/intraday-alert-validation-2026-11-07';SOURCE=ROOT/'data/history/intraday-study'
HORIZONS=(1,4,8,16,32);SH=timezone(timedelta(hours=8))
def timestamp(value):return datetime.fromisoformat(value.replace('Z','+00:00'))
def phase(value):
    day=timestamp(value).astimezone(SH).date().isoformat()
    return 'DEVELOPMENT' if day<'2026-07-01' else 'VALIDATION' if day<'2026-10-01' else 'RECENT_COMPARISON'
def dump(name,value):(OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def summary(rows):
    values=[r['netPct'] for r in rows];loss=sum(-v for v in values if v<0)
    return {'samples':len(rows),'contracts':len({r['contract'] for r in rows}),'meanNetPct':statistics.mean(values) if values else None,
        'winPct':sum(v>0 for v in values)/len(values)*100 if values else None,'profitFactor':sum(v for v in values if v>0)/loss if loss else None,
        'doubleCostMeanPct':statistics.mean(r['grossPct']-2*r['costPct'] for r in rows) if rows else None,
        'worstAdversePct':max((r['adversePct'] for r in rows),default=None)}
def main():
    OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/'results.json').exists():raise SystemExit('Completed intraday study exists; do not overwrite.')
    protocol={'version':'intraday-daily-ma-v1','horizons15mBars':HORIZONS,'selectionMinimumDevelopmentEvents':100,'selectionMinimumContracts':5,
        'conditions':['CROSS_DAY20_UP','CROSS_DAY20_DOWN','DAY5_PULLBACK_RECLAIM_PROXY','CROSS_DAY5_DOWN','BASE_LONG','BASE_SHORT'],
        'confirmation':'15-minute bar confirmed only by its successor; entry successor open; prior completed daily bars via day-serial successor boundaries.',
        'pullback':'15-minute OHLC touch-and-reclaim proxy, NOT the production tick-by-tick approach/touch rule.',
        'cost':'1bp notional each side plus one adverse tick each side; doubled sensitivity; not certified historical brokerage fees.',
        'sampling':'Signal bar volume >=100; one event at a time per condition/horizon/contract/phase; zero-volume execution windows rejected; labels cannot cross phase boundaries. Keep only latest lifecycle after any >365-calendar-day gap in daily history (reused exchange identifiers).',
        'split':'Before July 2026 development, July-September validation, October to collection cutoff recent retrospective comparison.',
        'selection':'Highest development mean net return once; no reselecting based on later windows; inadequate samples remain unselected.',
        'limitations':['Eight CURRENT active contracts, selected at collection date; survivorship and contract-life bias.','No independent prospective evidence.',
            '15-minute bars cannot establish tick-touch order or executable queue position.','Separate event returns, not a funded portfolio.'],
        'scriptSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    dump('protocol.json',protocol)
    collection=json.loads((SOURCE/'collection.json').read_text(encoding='utf-8'));inventory=[];groups=defaultdict(list);events=[]
    for item in collection['results']:
        if item['status']!='COLLECTED':continue
        file=SOURCE/item['file'];raw=file.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=item['sha256']:raise ValueError('Input changed since collection')
        data=json.loads(raw);m=data['bars15m'];d=data['barsDaily'];last={}
        if any(timestamp(a['timestamp'])>=timestamp(b['timestamp']) for rows in (m,d) for a,b in zip(rows,rows[1:])):raise ValueError('Unordered primary history')
        boundaries=[i for i in range(1,len(d)) if timestamp(d[i]['timestamp'])-timestamp(d[i-1]['timestamp'])>timedelta(days=365)]
        dropped=0
        if boundaries:
            cutoff=d[boundaries[-1]]['timestamp'];d=d[boundaries[-1]:];old=len(m);m=[b for b in m if timestamp(b['timestamp'])>=timestamp(cutoff)];dropped=old-len(m)
        days=[timestamp(b['timestamp']).timestamp() for b in d]
        inventory.append({**item,'priceTick':data['priceTick'],'rawSnapshotInLocalCache':True,'usable15mBars':len(m),'lifecyclePrefixBarsRejected':dropped,'usableStart':m[0]['timestamp'] if m else None})
        for i in range(1,len(m)-2):
            b=m[i];previous=m[i-1];next_bar=m[i+1];part=phase(b['timestamp'])
            if b['volume']<100:continue
            confirmed=timestamp(next_bar['timestamp']).timestamp();day_index=bisect.bisect_right(days,confirmed)-1
            if day_index<20 or timestamp(b['timestamp']).timestamp()<days[day_index]:continue
            reference=d[day_index-20:day_index]
            if any(x['volume']<=0 for x in reference):continue
            ma20=sum(x['price'] for x in reference)/20;ma5=sum(x['price'] for x in reference[-5:])/5
            candidates=[('BASE_LONG',1),('BASE_SHORT',-1)]
            if previous['price']<=ma20<b['price']:candidates.append(('CROSS_DAY20_UP',1))
            if previous['price']>=ma20>b['price']:candidates.append(('CROSS_DAY20_DOWN',-1))
            if previous['price']>=ma5>b['price']:candidates.append(('CROSS_DAY5_DOWN',-1))
            if previous['price']>ma5*1.002 and b['low']<=ma5*1.002 and b['high']>=ma5*.998 and b['price']>ma5:candidates.append(('DAY5_PULLBACK_RECLAIM_PROXY',1))
            for condition,direction in candidates:
                for horizon in HORIZONS:
                    key=(condition,horizon,part);end=i+horizon
                    if i<=last.get(key,-1) or end>=len(m)-1:continue
                    future=m[i+1:end+1]
                    if any(x['volume']<=0 or phase(x['timestamp'])!=part for x in future):continue
                    entry=future[0]['open'];exit=future[-1]['price'];gross=direction*(exit/entry-1)*100
                    cost=((entry+exit)*.0001+2*data['priceTick'])/entry*100
                    adverse=max(0,(entry-min(x['low'] for x in future))/entry*100 if direction==1 else (max(x['high'] for x in future)-entry)/entry*100)
                    value={'contract':data['contract'],'root':data['root'],'condition':condition,'direction':direction,'horizon':horizon,'phase':part,
                        'signalAt':b['timestamp'],'confirmedAt':next_bar['timestamp'],'entryAt':future[0]['timestamp'],'exitBarAt':future[-1]['timestamp'],
                        'dailyReferenceAt':reference[-1]['timestamp'],'formingDayAt':d[day_index]['timestamp'],
                        'grossPct':gross,'costPct':cost,'netPct':gross-cost,'adversePct':adverse}
                    groups[(condition,horizon,part)].append(value);events.append(value);last[key]=end
    report={}
    for condition in protocol['conditions']:
        grid={str(h):{s:summary(groups[(condition,h,s)]) for s in ('DEVELOPMENT','VALIDATION','RECENT_COMPARISON')} for h in HORIZONS}
        eligible=[h for h in HORIZONS if grid[str(h)]['DEVELOPMENT']['samples']>=100 and grid[str(h)]['DEVELOPMENT']['contracts']>=5]
        selected=max(eligible,key=lambda h:grid[str(h)]['DEVELOPMENT']['meanNetPct']) if eligible else None
        report[condition]={'horizons':grid,'developmentSelectedHorizon':selected,'selected':grid[str(selected)] if selected else None,
            'qualification':'EXPLORATORY_ONLY_NO_PROSPECTIVE_QUALIFICATION'}
    result={'version':protocol['version'],'status':'EXPLORATORY_NOT_LIVE_QUALIFIED','data':inventory,'source15mBars':sum(x['bars15m'] for x in inventory),'usable15mBars':sum(x['usable15mBars'] for x in inventory),
        'eventOutcomes':len(events),'conditions':report,'limitations':protocol['limitations']}
    dump('results.json',result)
    with gzip.open(OUT/'events.json.gz','wt',encoding='utf-8') as stream:json.dump(events,stream,ensure_ascii=False,allow_nan=False)
    print(json.dumps({'contracts':len(inventory),'bars15m':result['source15mBars'],'outcomes':len(events),
        'selection':{k:v['developmentSelectedHorizon'] for k,v in report.items()}},ensure_ascii=True),flush=True)
if __name__=='__main__':main()
