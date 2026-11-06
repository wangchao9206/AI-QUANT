"""Past-only features shared by outcome-first discovery and live alerts."""
import math

NAMES=('dayMA5DistancePct','dayMA20DistancePct','dayMA20Slope5Pct','dayMA5vs20Pct',
       'minuteMA20DistanceATR','minuteMA5vs20ATR','minuteMA20Slope5ATR','macdHistogramATR',
       'rsi14Simple','volumeRatio20','atrPct','closeLocation','bodyATR','return4ATR','oiChange5Pct')
LABELS={'LONG_ENTRY':'多头入场窗口','SHORT_ENTRY':'空头入场窗口','UP_MOVE':'后续上行','DOWN_MOVE':'后续下行',
        'LOW_TURN':'向上转折','HIGH_TURN':'向下转折','EXIT_LONG':'多头回撤风险','EXIT_SHORT':'空头反弹风险'}
def close(b):return b.get('price',b.get('close'))
def ema(values,period):
    output=[]
    for v in values:output.append(v if not output else output[-1]+2/(period+1)*(v-output[-1]))
    return output
def vector(minutes,days):
    if len(minutes)<120 or len(days)<25:return None
    m=minutes[-120:];d=days[-25:]
    try:
        p=[float(close(b)) for b in m];q=[float(close(b)) for b in d]
        if any(not math.isfinite(v) or v<=0 for v in p+q):return None
        if any(b['volume']<0 or not 0<b['low']<=min(b['open'],close(b))<=max(b['open'],close(b))<=b['high'] for b in m+d):return None
        ranges=[max(b['high']-b['low'],abs(b['high']-p[i]),abs(b['low']-p[i])) for i,b in enumerate(m[1:])]
        atr=sum(ranges[-14:])/14
        if atr<=0:return None
        ma5=sum(p[-5:])/5;ma20=sum(p[-20:])/20;old20=sum(p[-25:-5])/20
        day5=sum(q[-5:])/5;day20=sum(q[-20:])/20;old_day20=sum(q[:20])/20
        fast,slow=ema(p,12),ema(p,26);dif=[a-b for a,b in zip(fast,slow)];dea=ema(dif,9)
        changes=[b-a for a,b in zip(p[-15:],p[-14:])];gain=sum(max(v,0) for v in changes)/14;loss=sum(max(-v,0) for v in changes)/14
        rsi=100*gain/(gain+loss) if gain+loss else 50
        mean_volume=sum(b['volume'] for b in m[-21:-1])/20
        if mean_volume<=0:return None
        oi=m[-1].get('openInterest',m[-1].get('open_interest'));old_oi=m[-6].get('openInterest',m[-6].get('open_interest'))
        oi_change=(oi/old_oi-1)*100 if isinstance(oi,(int,float)) and isinstance(old_oi,(int,float)) and old_oi>0 else 0
        width=m[-1]['high']-m[-1]['low'];location=(p[-1]-m[-1]['low'])/width if width else .5
        values=[(p[-1]/day5-1)*100,(p[-1]/day20-1)*100,(day20/old_day20-1)*100,(day5/day20-1)*100,
            (p[-1]-ma20)/atr,(ma5-ma20)/atr,(ma20-old20)/atr,2*(dif[-1]-dea[-1])/atr,
            rsi,m[-1]['volume']/mean_volume,atr/p[-1]*100,location,(p[-1]-m[-1]['open'])/atr,(p[-1]-p[-5])/atr,oi_change]
        if any(not math.isfinite(v) for v in values):return None
        return {'values':dict(zip(NAMES,values)),'atr':atr,'oiKnown':oi is not None and old_oi is not None}
    except (TypeError,KeyError,ValueError,OverflowError):return None

def targets(current,past,future,atr,tick):
    """Future paths are labels only. Entry next open; same-bar TP/SL conservatively stops first."""
    entry=future[0]['open'];last8=close(future[7]);prices=[close(b) for b in future]
    def trade(direction):
        stop=entry-direction*atr;target=entry+direction*2*atr;won=False;exit=prices[-1]
        for b in future:
            if direction*(b['open']-stop)<=0:exit=b['open'];break
            if direction*(b['open']-target)>=0:exit=target;won=True;break
            if b['low']<=stop if direction>0 else b['high']>=stop:exit=stop;break
            if b['high']>=target if direction>0 else b['low']<=target:exit=target;won=True;break
        cost=((entry+exit)*.0001+2*tick)/entry*100;net=direction*(exit/entry-1)*100-cost
        return int(won and net>0),net
    long,lnet=trade(1);short,snet=trade(-1)
    low=min(b['low'] for b in future[:8]);high=max(b['high'] for b in future[:8])
    labels={'LONG_ENTRY':long,'SHORT_ENTRY':short,'UP_MOVE':int(last8>=entry+atr),'DOWN_MOVE':int(last8<=entry-atr),
        'LOW_TURN':int(current['low']<min(b['low'] for b in [*past[-4:],*future[:4]]) and last8>=close(current)+atr),
        'HIGH_TURN':int(current['high']>max(b['high'] for b in [*past[-4:],*future[:4]]) and last8<=close(current)-atr),
        'EXIT_LONG':int(low<=entry-1.5*atr and last8<=entry-.5*atr),
        'EXIT_SHORT':int(high>=entry+1.5*atr and last8>=entry+.5*atr)}
    return {'labels':labels,'longNetPct':lnet,'shortNetPct':snet,'maxAdverseLongATR':max(0,(entry-low)/atr),
            'maxAdverseShortATR':max(0,(high-entry)/atr)}

def matches(values,path):
    return all(values.get(r['feature']) is not None and (values[r['feature']]<=r['threshold'] if r['operator']=='LE' else values[r['feature']]>r['threshold']) for r in path)
