"""Pure completed-daily MACD and Shanghai trading-calendar alignment for research."""
from bisect import bisect_left
from datetime import date,datetime,time
import math

from scripts.backtest_fg701_intraday import SH


def current_contract_daily(daily,expiry_timestamp):
    """CZCE three-digit delivery codes can repeat after ten years; never bridge eras."""
    if not daily:
        raise ValueError('Empty provider daily history')
    dates=[datetime.fromtimestamp(b['datetime']/1e9,SH).date() for b in daily]
    if any(b<=a for a,b in zip(dates,dates[1:])):
        raise ValueError('Provider daily dates are not strictly increasing')
    boundaries=[i for i in range(1,len(dates)) if (dates[i]-dates[i-1]).days>366]
    start=boundaries[-1] if boundaries else 0
    current=daily[start:]
    expiry=datetime.fromtimestamp(expiry_timestamp,SH).date()
    if not expiry.year-2<=dates[start].year<=expiry.year or dates[-1]>expiry:
        raise ValueError('Daily era does not match current delivery maturity')
    if any((b-a).days>31 for a,b in zip(dates[start:],dates[start+1:])):
        raise ValueError('Unexplained gap within current delivery history')
    if any(b['id']!=a['id']+1 for a,b in zip(current,current[1:])):
        raise ValueError('Current delivery daily IDs are not contiguous')
    if len(current)<35:
        raise ValueError('Insufficient current-contract daily warmup')
    return current,{'status':'PASS','providerDailyBars':len(daily),'currentContractDailyBars':len(current),
                    'excludedHistoricalCodeReuseBars':start,'firstCurrentDate':dates[start].isoformat(),
                    'firstCurrentSourceId':int(current[0]['id']),'currentMaturity':expiry.isoformat(),
                    'priorEraEnd':dates[start-1].isoformat() if start else None,
                    'eraGapDays':(dates[start]-dates[start-1]).days if start else None}


def daily_macd(daily,fast=12,slow=26,signal=9,min_history=35,require_listing=True):
    if not 1<=fast<slow or signal<1 or min_history<1:
        raise ValueError('Invalid MACD periods')
    if not daily or (require_listing and daily[0]['id']!=0):
        raise ValueError('MACD requires daily history from listing ID zero')
    if any(b['id']!=a['id']+1 or b['datetime']<=a['datetime'] for a,b in zip(daily,daily[1:])):
        raise ValueError('Daily history IDs/timestamps are not contiguous')
    if any((datetime.fromtimestamp(b['datetime']/1e9,SH)-datetime.fromtimestamp(a['datetime']/1e9,SH)).days>366 for a,b in zip(daily,daily[1:])):
        raise ValueError('Historical delivery-code reuse must be separated before MACD')
    ema_fast=ema_slow=dea=None
    previous_delta=None
    last_cross_day,last_cross_side=None,0
    output=[]
    for n,b in enumerate(daily,1):
        close=b['close']
        if close is None or not math.isfinite(close) or close<=0:
            raise ValueError('Invalid daily close')
        day=datetime.fromtimestamp(b['datetime']/1e9,SH).date().isoformat()
        ema_fast=close if ema_fast is None else (close*2+(fast-1)*ema_fast)/(fast+1)
        ema_slow=close if ema_slow is None else (close*2+(slow-1)*ema_slow)/(slow+1)
        dif=ema_fast-ema_slow
        dea=dif if dea is None else (dif*2+(signal-1)*dea)/(signal+1)
        delta=dif-dea
        cross=1 if previous_delta is not None and previous_delta<=0<delta else -1 if previous_delta is not None and previous_delta>=0>delta else 0
        if cross:
            last_cross_day,last_cross_side=day,cross
        ready=n>=min_history
        side=(1 if delta>0 else -1 if delta<0 else 0) if ready else 0
        output.append({'date':day,'sourceId':int(b['id']),'close':close,'emaFast':ema_fast,
                       'emaSlow':ema_slow,'dif':dif,'dea':dea,'histogram':2*delta,
                       'allowedSide':side,'cross':cross,'lastCrossDate':last_cross_day,
                       'lastCrossSide':last_cross_side,'ready':ready,'historyBars':n,
                       'availableAt':datetime.combine(date.fromisoformat(day),time(15),SH).isoformat()})
        previous_delta=delta
    return output


def bind_daily_filter(bars,macd,calendar):
    dates=[r['date'] for r in macd]
    trading_dates=sorted(r['date'] for r in calendar if r['trading'])
    contexts={}
    output=[]
    for b in bars:
        day=b['tradingDay']
        if day not in contexts:
            index=bisect_left(dates,day)-1
            if index<0:
                raise ValueError('No previous completed daily MACD')
            known=macd[index]
            calendar_index=bisect_left(trading_dates,day)
            if calendar_index<=0 or trading_dates[calendar_index-1]!=known['date']:
                raise ValueError('Daily MACD is missing the previous actual trading date')
            contexts[day]={'tradingDay':day,'sourceDay':known['date'],'availableAt':known['availableAt'],
                           'dif':known['dif'],'dea':known['dea'],'histogram':known['histogram'],
                           'allowedSide':known['allowedSide'],'lastCrossDate':known['lastCrossDate'],
                           'lastCrossSide':known['lastCrossSide'],'historyBars':known['historyBars'],'ready':known['ready']}
        c=contexts[day]
        if not c['sourceDay']<day or datetime.fromisoformat(c['availableAt'])>b['timestamp']:
            raise ValueError('Daily MACD was not available at the intraday timestamp')
        output.append({**b,'allowedSide':c['allowedSide'],'dailySourceDay':c['sourceDay'],
                       'dailyDIF':c['dif'],'dailyDEA':c['dea'],'dailyMACD':c['histogram'],
                       'dailyAvailableAt':c['availableAt'],'dailyLastCrossDate':c['lastCrossDate']})
    return output,contexts


def verify_daily_overlap(minute_source,daily_source,last_day='2026-11-16'):
    if daily_source['symbol']!='CZCE.FG701':
        raise ValueError('Wrong delivery contract for daily MACD')
    new={datetime.fromtimestamp(b['datetime']/1e9,SH).date().isoformat():b for b in daily_source['daily']}
    checks=0
    for old in minute_source['daily']:
        day=datetime.fromtimestamp(old['datetime']/1e9,SH).date().isoformat()
        if day>last_day:
            continue
        observed=new.get(day)
        if observed is None or any(old[k]!=observed[k] for k in ('open','high','low','close','volume')):
            raise ValueError('Completed daily source mismatch: '+day)
        checks+=1
    return {'status':'PASS','overlappingCompletedDailyOHLCVChecks':checks,'throughDate':last_day}
