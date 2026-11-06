"""Causal daily features shared by research and live context. No future labels here."""
import math

CONDITIONS={
 'UP_TREND':('均线向上排列且 MA20 上行',1),
 'DOWN_TREND':('均线向下排列且 MA20 下行',-1),
 'UP_PULLBACK':('上升背景回踩 MA5 后收回',1),
 'DOWN_REBOUND':('下降背景反弹 MA5 后回落',-1),
 'BREAKOUT_UP':('收盘上穿此前日线 MA20',1),
 'BREAKOUT_DOWN':('收盘下穿此前日线 MA20',-1),
 'LOW_PIVOT':('低点经后续两根日线确认',1),
 'HIGH_PIVOT':('高点经后续两根日线确认',-1),
 'UP_EXHAUSTION':('20日新高放量收阴',-1),
 'DOWN_EXHAUSTION':('20日新低放量收阳',1),
}

def features(bars):
    if len(bars)<25:return None
    rows=bars[-25:]
    try:
        prices=[float(b.get('price',b.get('close'))) for b in rows]
        if any(not math.isfinite(v) or v<=0 for v in prices):return None
        for b in rows:
            if not all(math.isfinite(b[k]) for k in ('open','high','low','volume')) or b['volume']<0:return None
            close=float(b.get('price',b.get('close')))
            if not 0<b['low']<=min(b['open'],close)<=max(b['open'],close)<=b['high']:return None
        ma5=sum(prices[-5:])/5;ma20=sum(prices[-20:])/20;old20=sum(prices[:20])/20
        reference5=sum(prices[-6:-1])/5;reference20=sum(prices[-21:-1])/20
        last=rows[-1];close=prices[-1];volume_mean=sum(b['volume'] for b in rows[-21:-1])/20
        ratio=last['volume']/volume_mean if volume_mean>0 else None
        ranges=[max(b['high']-b['low'],abs(b['high']-prices[i]),abs(b['low']-prices[i])) for i,b in enumerate(rows[1:])]
        atr=sum(ranges[-14:])/14
        pivot=rows[-3];neighbors=[rows[i] for i in (-5,-4,-2,-1)]
        up=close>ma5>ma20 and ma20>old20;down=close<ma5<ma20 and ma20<old20
        states={
            'UP_TREND':up,'DOWN_TREND':down,
            'UP_PULLBACK':ma20>old20 and prices[-2]>reference5 and last['low']<=reference5<close,
            'DOWN_REBOUND':ma20<old20 and prices[-2]<reference5 and last['high']>=reference5>close,
            'BREAKOUT_UP':prices[-2]<=reference20<close,'BREAKOUT_DOWN':prices[-2]>=reference20>close,
            'LOW_PIVOT':all(pivot['low']<b['low'] for b in neighbors),
            'HIGH_PIVOT':all(pivot['high']>b['high'] for b in neighbors),
            'UP_EXHAUSTION':last['high']>max(b['high'] for b in rows[-21:-1]) and close<last['open'] and ratio is not None and ratio>=2,
            'DOWN_EXHAUSTION':last['low']<min(b['low'] for b in rows[-21:-1]) and close>last['open'] and ratio is not None and ratio>=2,
        }
        return {'ma5':ma5,'ma20':ma20,'ma20Slope5Pct':(ma20/old20-1)*100,'atr14':atr,
            'volumeRatio20':ratio,'distanceMA20Atr':(close-ma20)/atr if atr>0 else None,
            'regime':'UP' if up else 'DOWN' if down else 'MIXED','conditions':[k for k,v in states.items() if v]}
    except (KeyError,ValueError,TypeError,OverflowError):return None
