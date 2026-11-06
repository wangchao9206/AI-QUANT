"""Cross-timeframe watch conditions; daily reference excludes the forming day."""
from datetime import datetime
import math


def evaluate_entry_alerts(daily, closed, depth, previous, period, tolerance_pct, seconds=900):
    empty=({},[],{'dailyMA':None,'dailyReferenceStatus':'日线未就绪'})
    if not daily or daily.get('dataStatus')!='FRESH':return empty
    points=daily.get('points',[])
    if len(points)<period+1 or len(closed)<2:return empty
    bars=points[:-1]
    try:
        stamps=[datetime.fromisoformat(b['timestamp'].replace('Z','+00:00')).timestamp() for b in points]
        quote_at=datetime.fromisoformat(depth['dataTimestamp'].replace('Z','+00:00')).timestamp()
        daily_at=datetime.fromisoformat(daily['dataTimestamp'].replace('Z','+00:00')).timestamp()
        if not 0<=quote_at-daily_at<=15 or any(a>=b for a,b in zip(stamps,stamps[1:])) or stamps[-1]>quote_at:return empty
        prices=[b['price'] for b in bars[-period:]]
        if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<=0 for v in prices):return empty
        ma=sum(prices)/period;price=depth['lastPrice']
    except (KeyError,ValueError,TypeError):return empty
    reference=bars[-1]['timestamp'];bar=closed[-1];prev=closed[-2]
    state={'reference':reference,'period':period,'lastBar':bar['timestamp'],'lastPrice':price}
    metrics={'dailyMA':ma,'dailyMaPeriod':period,'dailyReferenceAt':reference,'dailyReferenceStatus':'READY'}
    if previous.get('reference')!=reference or previous.get('period')!=period:return state,[],metrics
    events=[]
    evidence={'triggerSeconds':seconds,'referencePeriod':'DAY','maPeriod':period,'dailyMA':ma,'dailyReferenceAt':reference,
              'referenceBasis':'COMPLETED_DAILY_BARS_ONLY','price':price}
    def add(rule,extra):events.append({'rule':rule,'variant':f'DAY_MA{period}',
        'key':f'{rule}:{period}:{bar["timestamp"] if rule!="DAILY_MA_PULLBACK" else depth["dataTimestamp"]}',
        'evidence':{**evidence,**extra}})
    # A successor confirms closure; do not replay old crossings after an outage.
    bar_at=datetime.fromisoformat(bar['timestamp'].replace('Z','+00:00')).timestamp()
    next_at=datetime.fromisoformat(depth['dataTimestamp'].replace('Z','+00:00')).timestamp()
    if previous.get('lastBar')!=bar['timestamp'] and bar_at>=stamps[-1] and 0<=next_at-bar_at-seconds<=max(15,seconds):
        if prev['price']<=ma<bar['price']:add('DAILY_MA_BREAKOUT_UP',{'close':bar['price'],'previousClose':prev['price'],'candleStart':bar['timestamp'],'confirmation':'BAR_CLOSE','opportunity':'LONG_ENTRY_WATCH'})
        if prev['price']>=ma>bar['price']:add('DAILY_MA_BREAKOUT_DOWN',{'close':bar['price'],'previousClose':prev['price'],'candleStart':bar['timestamp'],'confirmation':'BAR_CLOSE','opportunity':'LONG_EXIT_OR_SHORT_WATCH'})
    band=ma*tolerance_pct/100
    # Require an observed approach from above, rather than replaying the day's old low.
    if previous.get('lastPrice',price)>ma+band and ma-band<=price<=ma+band:
        add('DAILY_MA_PULLBACK',{'tolerancePct':tolerance_pct,'previousPrice':previous['lastPrice'],
            'confirmation':'INTRABAR_TOUCH','opportunity':'LONG_PULLBACK_WATCH'})
    return state,events,metrics
