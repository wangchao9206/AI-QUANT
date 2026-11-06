"""Versioned, observed-only rules. Closed bars drive technical signals; no trading hooks."""
from __future__ import annotations
import copy
import math
from algorithm_service.entry_alerts import evaluate_entry_alerts
from algorithm_service.research_context import evaluate_context,alert_assessment
from algorithm_service.outcome_monitor import evaluate_outcome
from algorithm_service.multifactor_monitor import evaluate_multifactor
from datetime import datetime, timezone

ALGORITHM_VERSION = 'depth-monitor-v5'
RULES = {
    'OUTCOME_PATTERN':'结果反推 · 入场／离场／拐点概率观察',
    'DAILY_RESEARCH_CONTEXT':'日线趋势／拐点研究观察（未获交易资格）',
    'DAILY_MA_BREAKOUT_UP':'收盘突破日线均线 · 做多观察',
    'DAILY_MA_BREAKOUT_DOWN':'收盘跌破日线均线 · 多头退出／做空观察',
    'DAILY_MA_PULLBACK':'盘中回踩日线均线 · 入场观察（未确认）',
    'PRICE_UP_60S':'60 秒涨幅超阈值', 'PRICE_DOWN_60S':'60 秒跌幅超阈值',
    'BIG_BUY':'大额买向成交增量', 'BIG_SELL':'大额卖向成交增量', 'BIG_NEUTRAL':'大额成交增量（方向未定）',
    'VOLUME_SPIKE':'成交量异动', 'VOLUME_BREAKOUT_UP':'放量突破前高', 'VOLUME_BREAKOUT_DOWN':'放量跌破前低',
    'MA_BREAKOUT_UP':'放量突破均线', 'MA_BREAKOUT_DOWN':'放量跌破均线',
    'BOLL_BREAKOUT_UP':'放量突破布林上轨', 'BOLL_BREAKOUT_DOWN':'放量跌破布林下轨',
    'DONCHIAN_UP':'放量突破唐奇安上轨', 'DONCHIAN_DOWN':'放量跌破唐奇安下轨',
    'KELTNER_UP':'放量突破肯特纳上轨', 'KELTNER_DOWN':'放量跌破肯特纳下轨',
    'MACD_GOLDEN':'MACD 金叉', 'MACD_DEAD':'MACD 死叉',
    'MACD_BOTTOM':'MACD 底背离（已确认）', 'MACD_TOP':'MACD 顶背离（已确认）',
    'ATR_MOVE':'ATR 价格异动', 'DEPTH_IMBALANCE':'可见挂单失衡', 'SPREAD_SPIKE':'买卖价差异动',
}


def number(value):
    return isinstance(value, (float,int)) and not isinstance(value,bool) and math.isfinite(value)


def stamp(value):
    return datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()


def ema(values, period):
    result=[]
    for value in values:
        result.append(value if not result else value*2/(period+1)+result[-1]*(1-2/(period+1)))
    return result


def macd(closes):
    fast,slow=ema(closes,12),ema(closes,26)
    dif=[a-b for a,b in zip(fast,slow)]
    return dif,ema(dif,9)


def technical_signals(bars, seconds, params):
    """Input contains only successor-confirmed bars, never the forming last bar."""
    events=[]
    if len(bars)<2:return events
    current,previous=bars[-1],bars[-2]
    closes=[b['price'] for b in bars]
    n=params['lookback'];prior=bars[-n-1:-1]
    volume_mean=sum(b['volume'] for b in prior)/n if len(prior)==n else None
    volume_ratio=current['volume']/volume_mean if volume_mean and volume_mean>0 else None
    volume_ok=volume_ratio is not None and volume_ratio>=params['volumeMultiple']
    evidence={'candleStart':current['timestamp'],'seconds':seconds,'close':current['price'],
              'volume':current['volume'],'priorMeanVolume':volume_mean,'volumeRatio':volume_ratio}
    def add(rule, extra=None, variant=''):
        events.append({'rule':rule,'variant':variant,'key':f'{rule}:{variant}:{current["timestamp"]}',
                       'evidence':{**evidence,**(extra or {})}})
    def band(up,down,upper,lower,name):
        if volume_ok and previous['price']<=upper<current['price']:add(up,{'channel':name,'threshold':upper})
        if volume_ok and previous['price']>=lower>current['price']:add(down,{'channel':name,'threshold':lower})
    if volume_ok:add('VOLUME_SPIKE')
    if len(prior)==n:
        high=max(b['high'] for b in prior);low=min(b['low'] for b in prior)
        band('VOLUME_BREAKOUT_UP','VOLUME_BREAKOUT_DOWN',high,low,'前 N 根高低点')
        band('DONCHIAN_UP','DONCHIAN_DOWN',high,low,'Donchian')
        mean=sum(b['price'] for b in prior)/n
        std=math.sqrt(sum((b['price']-mean)**2 for b in prior)/n)
        band('BOLL_BREAKOUT_UP','BOLL_BREAKOUT_DOWN',mean+params['bollStd']*std,mean-params['bollStd']*std,'Bollinger')
    for period in params['maPeriods']:
        if len(closes)<period+1:continue
        old=sum(closes[-period-1:-1])/period;new=sum(closes[-period:])/period
        if volume_ok and previous['price']<=old and current['price']>new:add('MA_BREAKOUT_UP',{'period':period,'previousMA':old,'currentMA':new},f'MA{period}')
        if volume_ok and previous['price']>=old and current['price']<new:add('MA_BREAKOUT_DOWN',{'period':period,'previousMA':old,'currentMA':new},f'MA{period}')
    ranges=[max(b['high']-b['low'],abs(b['high']-a['price']),abs(b['low']-a['price'])) for a,b in zip(bars,bars[1:])]
    if len(ranges)>=n+1:
        atr=sum(ranges[-n-1:-1])/n
        center=ema(closes,n)[-2]
        band('KELTNER_UP','KELTNER_DOWN',center+params['atrMultiple']*atr,center-params['atrMultiple']*atr,'Keltner / EMA + mean TR')
        if atr>0 and abs(current['price']-previous['price'])>=params['atrMultiple']*atr:
            add('ATR_MOVE',{'atr':atr,'priceChange':current['price']-previous['price']})
    if len(closes)<35:return events
    dif,dea=macd(closes)
    tolerance=max(1,abs(closes[-1]))*1e-10
    if dif[-2]-dea[-2]<=tolerance and dif[-1]-dea[-1]>tolerance:add('MACD_GOLDEN',{'dif':dif[-1],'dea':dea[-1],'previousDIF':dif[-2],'previousDEA':dea[-2]})
    if dif[-2]-dea[-2]>=-tolerance and dif[-1]-dea[-1]<-tolerance:add('MACD_DEAD',{'dif':dif[-1],'dea':dea[-1],'previousDIF':dif[-2],'previousDEA':dea[-2]})
    right=params['pivotBars'];pivot=len(bars)-right-1
    if pivot<right+5:return events
    def is_pivot(i,key,lower):
        value=bars[i][key];neighbors=[bars[j][key] for j in range(i-right,i+right+1) if j!=i]
        return all(value<v for v in neighbors) if lower else all(value>v for v in neighbors)
    for key,lower,rule in [('low',True,'MACD_BOTTOM'),('high',False,'MACD_TOP')]:
        if not is_pivot(pivot,key,lower):continue
        prior_pivots=[i for i in range(max(right,pivot-100),pivot-4) if is_pivot(i,key,lower)]
        if not prior_pivots:continue
        first=prior_pivots[-1]
        valid=(bars[pivot][key]<bars[first][key] and dif[first]<dif[pivot]<0) if lower else (bars[pivot][key]>bars[first][key] and dif[first]>dif[pivot]>0)
        if valid:add(rule,{'firstPivot':bars[first]['timestamp'],'secondPivot':bars[pivot]['timestamp'],
                           'firstPrice':bars[first][key],'secondPrice':bars[pivot][key],
                           'firstDIF':dif[first],'secondDIF':dif[pivot],'confirmationBar':current['timestamp'],
                           'rightClosedBars':right})
    return events


def historical_metrics(closed, depth, params, seconds):
    """Observed depth and successor-confirmed bars; unavailable windows stay null."""
    closes=[b['price'] for b in closed]
    last=closed[-1] if closed else None
    n=params['lookback'];prior=closed[-n-1:-1]
    mean=sum(b['volume'] for b in prior)/n if len(prior)==n else None
    bids=depth.get('bids',[]);asks=depth.get('asks',[])
    def level(rows):
        return next((r['price'] for r in rows if r.get('level')==1 and number(r.get('price')) and r['price']>0),None)
    bid,ask=level(bids),level(asks)
    def lots(rows):
        return sum(r['volume'] for r in rows if number(r.get('price')) and r['price']>0 and number(r.get('volume')) and r['volume']>=0)
    buy,sell=lots(bids),lots(asks)
    metrics={'lastPrice':depth.get('lastPrice'),'seconds':seconds,'closedBarAt':last['timestamp'] if last else None,
        'close':last['price'] if last else None,'volume':last['volume'] if last else None,
        'priorMeanVolume':mean,'volumeRatio':last['volume']/mean if last and mean and mean>0 else None,
        'bidLots':buy,'askLots':sell,'spread':ask-bid if bid is not None and ask is not None and ask>=bid else None,
        'depthImbalance':(buy-sell)/(buy+sell) if bid is not None and ask is not None and ask>=bid and buy+sell>0 else None,
        'closedBars':len(closed)}
    for period in (5,10,20,60,180):metrics['ma'+str(period)]=sum(closes[-period:])/period if len(closes)>=period else None
    metrics.update(dif=None,dea=None,macdHistogram=None,atr=None,bollUpper=None,bollLower=None)
    if len(closes)>=35:
        dif,dea=macd(closes);metrics.update(dif=dif[-1],dea=dea[-1],macdHistogram=2*(dif[-1]-dea[-1]))
    if len(closes)>=n:
        center=sum(closes[-n:])/n;std=math.sqrt(sum((v-center)**2 for v in closes[-n:])/n)
        metrics.update(bollUpper=center+params['bollStd']*std,bollLower=center-params['bollStd']*std)
    ranges=[max(b['high']-b['low'],abs(b['high']-a['price']),abs(b['low']-a['price'])) for a,b in zip(closed,closed[1:])]
    if len(ranges)>=n:metrics['atr']=sum(ranges[-n:])/n
    return metrics


def evaluate(frame, previous, params, seconds, now=None):
    now=now or datetime.now(timezone.utc);now_seconds=now.timestamp()
    state=copy.deepcopy(previous or {});events=[]
    depth=frame.get('depth') or {};chart=frame.get('chart') or {}
    quote_time=depth.get('dataTimestamp');price=depth.get('lastPrice');points=chart.get('points') or []
    try:
        quote_at=stamp(quote_time);chart_at=stamp(chart['dataTimestamp'])
        fresh=(depth.get('dataStatus')=='FRESH' and chart.get('dataStatus')=='FRESH'
               and 0<=now_seconds-quote_at<=15 and 0<=now_seconds-chart_at<=15
               and number(price) and price>0 and len(points)>=2)
    except (ValueError,TypeError,KeyError):fresh=False
    if not fresh:
        return {'status':'STALE','message':'行情未就绪、休市或过时，暂停触发。','state':{'cooldowns':state.get('cooldowns',{}),'research':{**state.get('research',{}),'pending':[]},'outcome':state.get('outcome',{})},'events':[],
                'sourceTimestamp':quote_time,'metrics':{'windowReady':False},'algorithmVersion':ALGORITHM_VERSION}
    # Validate the complete indicator input rather than silently skipping corrupt bars.
    for i,bar in enumerate(points):
        try:
            valid=all(number(bar[k]) for k in ('price','open','high','low','volume')) and bar['volume']>=0
            valid=valid and 0<bar['low']<=min(bar['open'],bar['price'])<=max(bar['open'],bar['price'])<=bar['high']
            valid=valid and stamp(bar['timestamp'])<=quote_at and (i==0 or stamp(points[i-1]['timestamp'])<stamp(bar['timestamp']))
        except (ValueError,KeyError,TypeError):valid=False
        if not valid:return {'status':'ERROR','message':'K 线校验失败，暂停触发。','state':{},'events':[],'sourceTimestamp':quote_time,'metrics':{},'algorithmVersion':ALGORITHM_VERSION}
    closed=points[:-1];last_bar=closed[-1]['timestamp']
    snapshot_metrics=historical_metrics(closed,depth,params,seconds)
    opportunity_state,opportunities,opportunity_metrics=evaluate_entry_alerts(frame.get('daily'),closed,depth,state.get('opportunities',{}),params.get('dailyMaPeriod',20),params.get('pullbackTolerancePct',.2),seconds)
    if any(rule.startswith('DAILY_') for rule in params['rules']):snapshot_metrics.update(opportunity_metrics)
    ticks=[]
    for tick in depth.get('trades',[]):
        try:
            if (number(tick.get('price')) and tick['price']>0 and number(tick.get('volume')) and tick['volume']>0
                    and 0<=now_seconds-stamp(tick['timestamp'])<=15 and stamp(tick['timestamp'])<=quote_at):ticks.append(tick)
        except (ValueError,KeyError,TypeError):continue
    def tick_key(t):return f'{t.get("id","")}:{t["timestamp"]}'
    last_quote=state.get('lastQuoteAt')
    initialize=not state.get('initialized') or (last_quote is not None and (quote_at-last_quote>15 or quote_at<last_quote))
    research_state,research_events,research_metrics=evaluate_context(frame.get('daily'),state.get('research',{}),opportunity_metrics.get('dailyMA') is not None,not initialize)
    if 'OUTCOME_PATTERN' not in params['rules']:outcome_state,outcome_events,outcome_metrics=({},[],{})
    elif params.get('outcomeModel')=='MULTI':
        outcome_state,outcome_events,outcome_metrics=evaluate_multifactor(frame,state.get('outcome',{}),seconds,params.get('outcomeTarget','ALL'),params.get('outcomeEvidence','IMPROVED'),params.get('outcomeFamily','COMBINED'))
    else:outcome_state,outcome_events,outcome_metrics=evaluate_outcome(frame,state.get('outcome',{}),seconds,params.get('outcomeTarget','ALL'),params.get('outcomeEvidence','IMPROVED'))
    if 'OUTCOME_PATTERN' in params['rules']:snapshot_metrics['outcome']=outcome_metrics
    if 'DAILY_RESEARCH_CONTEXT' in params['rules']:snapshot_metrics['research']=research_metrics
    if initialize:
        state={'initialized':True,'lastQuoteAt':quote_at,'lastBar':last_bar,'samples':[{'t':quote_at,'p':price}],
               'seenTicks':[tick_key(t) for t in ticks][-512:],'hot':[],'cooldowns':state.get('cooldowns',{}),'opportunities':opportunity_state,'research':research_state,'outcome':outcome_state}
        model_only=params['rules']==['OUTCOME_PATTERN']
        return {'status':'READY' if model_only and outcome_metrics.get('status')=='READY' else 'WARMING','message':outcome_metrics.get('message','概率观测数据未就绪。') if model_only else '已建立实时基线；60 秒涨跌窗口预热中，不补发历史触发。',
                'state':state,'events':[{**e,'observedAt':quote_time,'algorithmVersion':ALGORITHM_VERSION} for e in outcome_events],'sourceTimestamp':quote_time,'metrics':{**snapshot_metrics,'windowReady':False},'algorithmVersion':ALGORITHM_VERSION}
    samples=[s for s in state.get('samples',[]) if quote_at-180<=s['t']<=quote_at]
    if not samples or quote_at>samples[-1]['t']:samples.append({'t':quote_at,'p':price})
    elif quote_at==samples[-1]['t']:samples[-1]['p']=price
    samples=samples[-180:]
    # Wait for a full observed minute, then use the first quote inside that minute.
    # A quote older than the window can falsely attribute a >60s move to one minute.
    covered=bool(samples) and quote_at-samples[0]['t']>=60
    base=next((s for s in samples if 0<=s['t']-(quote_at-60)<=10),None) if covered else None
    change=(price-base['p'])/base['p']*100 if base and base['p']>0 else None
    hot=set();candidates=[*opportunities,*research_events,*outcome_events]
    def live(rule,evidence,variant='',key=None):
        candidates.append({'rule':rule,'variant':variant,'key':key or f'{rule}:{quote_time}', 'evidence':evidence})
    for rule,condition in [('PRICE_UP_60S',change is not None and change>params['jumpPct']+1e-9),('PRICE_DOWN_60S',change is not None and change<-params['jumpPct']-1e-9)]:
        if condition:
            hot.add(rule)
            if rule not in state.get('hot',[]):live(rule,{'price':price,'baselinePrice':base['p'],'baselineTimestamp':datetime.fromtimestamp(base['t'],timezone.utc).isoformat(),'windowSeconds':quote_at-base['t'],'changePct':change,'thresholdPct':params['jumpPct']})
    seen=set(state.get('seenTicks',[]))
    for tick in sorted(ticks,key=lambda t:stamp(t['timestamp'])):
        key=tick_key(tick)
        if key in seen:continue
        seen.add(key)
        if tick['volume']>=params['bigLots']:
            rule='BIG_BUY' if tick.get('side')=='BUY' else 'BIG_SELL' if tick.get('side')=='SELL' else 'BIG_NEUTRAL'
            live(rule,{'tickTimestamp':tick['timestamp'],'tickId':tick.get('id'),'price':tick['price'],'lots':tick['volume'],
                       'thresholdLots':params['bigLots'],'directionBasis':'TICK_PRICE_VS_BID_ASK_ESTIMATE'},key=f'{rule}:{key}')
    bids=[r for r in depth.get('bids',[]) if number(r.get('price')) and r['price']>0 and number(r.get('volume')) and r['volume']>=0]
    asks=[r for r in depth.get('asks',[]) if number(r.get('price')) and r['price']>0 and number(r.get('volume')) and r['volume']>=0]
    bid=next((r['price'] for r in bids if r['level']==1),None);ask=next((r['price'] for r in asks if r['level']==1),None)
    spread=ask-bid if bid is not None and ask is not None and ask>=bid else None
    bid_lots=sum(r['volume'] for r in bids);ask_lots=sum(r['volume'] for r in asks)
    imbalance=(bid_lots-ask_lots)/(bid_lots+ask_lots) if spread is not None and bid_lots+ask_lots>0 else None
    if imbalance is not None and abs(imbalance)>=.6:
        key='DEPTH_IMBALANCE:'+('BUY' if imbalance>0 else 'SELL');hot.add(key)
        if key not in state.get('hot',[]):live('DEPTH_IMBALANCE',{'imbalance':imbalance,'bidLots':bid_lots,'askLots':ask_lots,'bidLevels':len(bids),'askLevels':len(asks)},variant=key)
    spreads=state.get('spreads',[])[-20:]
    mean_spread=sum(spreads)/len(spreads) if len(spreads)>=10 else None
    if spread is not None and mean_spread and spread>=3*mean_spread:
        hot.add('SPREAD_SPIKE')
        if 'SPREAD_SPIKE' not in state.get('hot',[]):live('SPREAD_SPIKE',{'spread':spread,'priorMeanSpread':mean_spread,'ratio':spread/mean_spread})
    if spread is not None and spread>0 and quote_at>state.get('lastQuoteAt',0):spreads.append(spread)
    if last_bar!=state.get('lastBar') and 0<=quote_at-stamp(last_bar)-seconds<=max(15,seconds):
        candidates.extend(technical_signals(closed,seconds,params))
    cooldowns=state.get('cooldowns',{})
    for item in candidates:
        if item['rule'] not in params['rules']:continue
        cooldown_key=item['rule']+':'+item.get('variant','')
        # Tick IDs are deduplicated independently; do not hide a different real large increment.
        if not item['rule'].startswith('BIG_') and quote_at-cooldowns.get(cooldown_key,0)<params['cooldownSeconds']:continue
        cooldowns[cooldown_key]=quote_at
        assessment=alert_assessment(item['rule'],params.get('dailyMaPeriod',20),seconds)
        if assessment is not None:item={**item,'evidence':{**item.get('evidence',{}),'statisticalAssessment':assessment}}
        events.append({**item,'label':item.get('label',RULES[item['rule']]),'observedAt':quote_time,'algorithmVersion':ALGORITHM_VERSION})
    state.update(lastQuoteAt=quote_at,lastBar=last_bar,opportunities=opportunity_state,research=research_state,outcome=outcome_state,samples=samples,seenTicks=sorted(seen,key=lambda k:stamp(k.split(':',1)[1]))[-512:],hot=sorted(hot),
                 cooldowns=cooldowns,spreads=spreads[-20:])
    metrics={**snapshot_metrics,'windowReady':base is not None,'change60sPct':change,'closedBars':len(closed),'depthImbalance':imbalance,'spread':spread}
    daily_only=all(rule.startswith('DAILY_') for rule in params['rules'])
    daily_pending=(any(rule.startswith('DAILY_') for rule in params['rules']) and opportunity_metrics.get('dailyMA') is None) or ('DAILY_RESEARCH_CONTEXT' in params['rules'] and research_metrics.get('status')!='READY')
    ready=(base is not None or daily_only or 'OUTCOME_PATTERN' in params['rules']) and not daily_pending and ('OUTCOME_PATTERN' not in params['rules'] or outcome_metrics.get('status')=='READY')
    message='日线数据未就绪或历史不足，跨周期预警暂停；等待真实日线。' if daily_pending else '日线条件监控运行中；盘中触及不等于收盘确认。' if daily_only else '监控运行中。' if base else '技术与成交规则运行；60 秒涨跌窗口预热中。'
    if 'OUTCOME_PATTERN' in params['rules']:message=outcome_metrics.get('message','模型周期、品种或活跃度不在本次研究范围内。')
    return {'status':'READY' if ready else 'WARMING','message':message,
            'state':state,'events':events[:100],'sourceTimestamp':quote_time,'metrics':metrics,'algorithmVersion':ALGORITHM_VERSION}
