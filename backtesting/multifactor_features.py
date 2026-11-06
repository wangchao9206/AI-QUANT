"""Causal multi-period indicators and native Chan snapshots, shared with live alerts.

Higher periods are complete Shanghai clock buckets, not exchange-specific K lines.
Native structures use a fixed rolling window; only structures observed by now enter.
"""
import math
from datetime import datetime
from chanlun_worker.native import NativeEngine, VERSION, PARAMETERS
from backtesting.outcome_features import close, ema, vector

VERSION_ID = 'multifactor-chan-v1'
WINDOW = 600
TECH_NAMES = ('ma5vs20ATR','ma10vs60ATR','ma20Slope5ATR','macdHistATR',
              'macdHistChangeATR','rsi14','stoch14','bollZ20','bollWidth20Pct',
              'donchian20Position','priorHigh20DistanceATR','priorLow20DistanceATR',
              'volumeRatio20','volumeAcceleration5','vwapCloseProxy20DistanceATR',
              'obv20Normalized','rangeExpansion14','efficiency20','atrPct',
              'oiChange5Pct','oiKnown')
CHAN_NAMES = ('penDirection','penAge','segmentDirection','fractalDirection','fractalAge',
              'zoneKnown','zonePositionATR','zoneWidthATR','penAreaRatio',
              'B1','S1','B2','S2','B3','S3')
BASE_NAMES = ('dayMA5DistancePct','dayMA20DistancePct','dayMA20Slope5Pct','dayMA5vs20Pct')
NAMES = (*BASE_NAMES, 'dayMA10DistancePct','dayMA60DistancePct','dayMA60Slope5Pct',
         *(f'{period}.{name}' for period in ('m15','m30','m60') for name in (*TECH_NAMES,*CHAN_NAMES)))
FAMILIES = {
    'INDICATORS_15': tuple(n for n in NAMES if n.startswith(('day','m15.')) and n.split('.')[-1] not in CHAN_NAMES),
    'INDICATORS_MULTI': tuple(n for n in NAMES if n.split('.')[-1] not in CHAN_NAMES),
    'CHAN_ONLY': tuple(n for n in NAMES if n.split('.')[-1] in CHAN_NAMES),
    'COMBINED': NAMES,
}

def stamp(value):
    return datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()

def aggregate(bars, minutes):
    """Drop incomplete/gapped clock buckets; attach the true earliest availability."""
    ratio=minutes//15; groups={}
    for bar in bars:
        t=stamp(bar['timestamp']); key=int((t+8*3600)//(minutes*60))
        groups.setdefault(key,[]).append(bar)
    output=[]
    for key, group in groups.items():
        begin=key*minutes*60-8*3600
        if len(group)!=ratio or any(stamp(b['timestamp'])!=begin+i*900 for i,b in enumerate(group)):
            continue
        last=group[-1]
        output.append({'timestamp':group[0]['timestamp'],'open':group[0]['open'],
                       'high':max(b['high'] for b in group),'low':min(b['low'] for b in group),
                       'price':close(last),'volume':sum(b['volume'] for b in group),
                       'openInterest':last.get('openInterest',last.get('open_interest')),
                       'availableAt':begin+minutes*60})
    return output

def technical(bars):
    if len(bars)<60:return None
    bars=bars[-120:]; p=[float(close(b)) for b in bars]; n=len(bars); last=bars[-1]
    if any(not math.isfinite(v) or v<=0 for v in p):return None
    tr=[max(b['high']-b['low'],abs(b['high']-p[i]),abs(b['low']-p[i])) for i,b in enumerate(bars[1:])]
    atr=sum(tr[-14:])/14
    if atr<=0:return None
    mean=lambda xs:sum(xs)/len(xs)
    ma5,ma10,ma20,ma60=[mean(p[-k:]) for k in (5,10,20,60)]
    old20=mean(p[-25:-5]); fast,slow=ema(p,12),ema(p,26)
    dif=[a-b for a,b in zip(fast,slow)]; dea=ema(dif,9); hist=[2*(a-b) for a,b in zip(dif,dea)]
    changes=[b-a for a,b in zip(p[-15:],p[-14:])]
    gain=sum(max(v,0) for v in changes); loss=sum(max(-v,0) for v in changes)
    low14=min(b['low'] for b in bars[-14:]); high14=max(b['high'] for b in bars[-14:])
    sd=math.sqrt(mean([(v-ma20)**2 for v in p[-20:]]))
    prior=bars[-21:-1]; hi=max(b['high'] for b in prior); lo=min(b['low'] for b in prior)
    volumes=[b['volume'] for b in bars]; avgvol=mean(volumes[-21:-1]); oldvol=mean(volumes[-10:-5])
    if avgvol<=0 or oldvol<=0 or sum(volumes[-20:])<=0:return None
    proxy=sum(close(b)*b['volume'] for b in bars[-20:])/sum(volumes[-20:])
    obv=sum((1 if p[i]>p[i-1] else -1 if p[i]<p[i-1] else 0)*volumes[i] for i in range(n-20,n))
    travel=sum(abs(b-a) for a,b in zip(p[-21:],p[-20:]))
    oi=last.get('openInterest',last.get('open_interest')); prev=bars[-6].get('openInterest',bars[-6].get('open_interest'))
    known=isinstance(oi,(int,float)) and isinstance(prev,(int,float)) and prev>0
    values=((ma5-ma20)/atr,(ma10-ma60)/atr,(ma20-old20)/atr,hist[-1]/atr,
            (hist[-1]-hist[-2])/atr,100*gain/(gain+loss) if gain+loss else 50,
            100*(p[-1]-low14)/(high14-low14) if high14>low14 else 50,
            (p[-1]-ma20)/sd if sd else 0,4*sd/ma20*100,
            (p[-1]-lo)/(hi-lo) if hi>lo else .5,(p[-1]-hi)/atr,(p[-1]-lo)/atr,
            volumes[-1]/avgvol,mean(volumes[-5:])/oldvol,(p[-1]-proxy)/atr,
            obv/sum(volumes[-20:]),(last['high']-last['low'])/atr,
            abs(p[-1]-p[-21])/travel if travel else 0,atr/p[-1]*100,
            (oi/prev-1)*100 if known else 0,int(known))
    if any(not math.isfinite(v) for v in values):return None
    return dict(zip(TECH_NAMES,values)),atr

def chan(bars,atr):
    """Snapshot after final input push; never reuse a later-mutated candidate."""
    engine=NativeEngine(); bars=bars[-120:]
    for i,b in enumerate(bars):
        engine.push({'index':i,'timestamp':b['timestamp'],'open':b['open'],'high':b['high'],
                     'low':b['low'],'close':close(b),'volume':b['volume']})
    i=len(bars)-1; p=close(bars[-1]); pen=engine.pens[-1] if engine.pens else None
    segment=engine.segments.segments[-1] if engine.segments.segments else None
    fractal=engine.fractals[-1] if engine.fractals else None
    zone=engine.zones.zones[-1] if engine.zones.zones else None
    ratio=0
    if len(engine.pens)>=3:
        previous=engine.pens[-3]; current=engine.pens[-1]
        old=engine.zones.area(previous)
        if old>0:ratio=min(8,engine.zones.area(current)/old)
    values=[pen.direction if pen else 0,min(120,i-pen.observed) if pen else 120,
            segment.direction if segment else 0,-fractal.kind if fractal else 0,
            min(120,i-fractal.observed) if fractal else 120,int(zone is not None),
            ((p-zone['high']) if p>zone['high'] else (p-zone['low']) if p<zone['low'] else 0)/atr if zone else 0,
            (zone['high']-zone['low'])/atr if zone else 0,ratio]
    values.extend(int(any(s['signalType']==name and s['signalState']=='CANDIDATE'
                         and 0<=i-s['candidateObservedIndex']<=8 for s in engine.zones.signals))
                  for name in ('B1','S1','B2','S2','B3','S3'))
    return dict(zip(CHAN_NAMES,values))

def context(bars):
    result=technical(bars)
    if result is None:return None
    values,atr=result
    return {**values,**chan(bars,atr)}

def extended_vector(minutes,days):
    """600-bar rolling origin is explicit and identical offline and in production."""
    if len(minutes)<WINDOW or len(days)<65:return None
    minutes=minutes[-WINDOW:]
    availability=stamp(minutes[-1]['timestamp'])+900
    periods={'m15':minutes[-120:]}
    for period in (30,60):
        periods[f'm{period}']=[b for b in aggregate(minutes,period) if b['availableAt']<=availability][-120:]
    contexts={name:context(bars) for name,bars in periods.items()}
    return combine(minutes,days,contexts,{name:len(bars) for name,bars in periods.items()})

def combine(minutes,days,contexts,counts):
    """Same composition for cached historical contexts and uncached live windows."""
    if len(minutes)<WINDOW or len(days)<65 or any(v is None for v in contexts.values()):return None
    base=vector(minutes,days)
    if base is None:return None
    q=[float(close(b)) for b in days[-65:]]
    if any(not math.isfinite(v) or v<=0 for v in q):return None
    ma10=sum(q[-10:])/10; ma60=sum(q[-60:])/60; old60=sum(q[:60])/60
    price=close(minutes[-1])
    values={name:base['values'][name] for name in BASE_NAMES}
    values.update(dayMA10DistancePct=(price/ma10-1)*100,dayMA60DistancePct=(price/ma60-1)*100,
                  dayMA60Slope5Pct=(ma60/old60-1)*100)
    for name,result in contexts.items():
        values.update({f'{name}.{key}':value for key,value in result.items()})
    return {'values':values,'atr':base['atr'],
            'contextBars':counts,
            'chanProfile':{'version':VERSION,'parameters':PARAMETERS,'origin':'ROLLING_600_15M_THEN_LAST_120_PER_PERIOD'}}
