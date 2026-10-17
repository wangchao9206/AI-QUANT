"""Cross-market overview: independent snapshots, without a selected instrument."""
from __future__ import annotations

import math
from datetime import datetime, timedelta

from data.evidence_feed import SHANGHAI_TZ
from data.history_manager import CORE_FUTURES_SYMBOLS
from data.radar_feed import PublicRadarFeed, RadarCache
from data.trading_day import completed_daily_bar


STRATEGIES = [
    ('MOMENTUM_BREAKOUT','放量通道突破','收盘突破前20日高低点，同向 MA60，成交量大于前10日均量的1.05倍'),
    ('BOLLINGER_REVERSAL','布林均值回归','15日均值 ± 2.2倍总体标准差，收盘触及轨道'),
    ('DUAL_THRUST','Dual Thrust','前4日区间，k=0.5，收盘突破当日开盘价轨道并顺 MA60'),
]


def strategy_conditions(bars):
    """Flat-position entry conditions matching the three named backtest defaults."""
    if len(bars)<61:
        return []
    b=bars[-1]; previous=bars[:-1]
    ma60=sum(x.close for x in bars[-60:])/60
    hi=max(x.high for x in previous[-20:]); lo=min(x.low for x in previous[-20:])
    avg=sum(x.volume for x in previous[-10:])/10
    volume_ratio=b.volume/avg if avg>0 else None
    momentum='BUY' if b.close>hi and b.close>ma60 and avg>0 and b.volume>avg*1.05 else 'SELL' if b.close<lo and b.close<ma60 and avg>0 and b.volume>avg*1.05 else 'HOLD'
    closes=[x.close for x in bars[-15:]]; mean=sum(closes)/15
    std=math.sqrt(sum((x-mean)**2 for x in closes)/15)
    # Flat series has no useful volatility boundary.
    lower,upper=mean-2.2*std,mean+2.2*std
    boll='BUY' if std>0 and b.close<=lower else 'SELL' if std>0 and b.close>=upper else 'HOLD'
    window=previous[-4:]
    rng=max(max(x.high for x in window)-min(x.close for x in window),max(x.close for x in window)-min(x.low for x in window))
    buy,sell=b.open+.5*rng,b.open-.5*rng
    dual='BUY' if b.close>buy and b.close>ma60 else 'SELL' if b.close<sell and b.close<ma60 else 'HOLD'
    return [
        {'strategy':'MOMENTUM_BREAKOUT','signal':momentum,'lower':lo,'upper':hi,'volumeRatio':round(volume_ratio,2) if volume_ratio is not None else None},
        {'strategy':'BOLLINGER_REVERSAL','signal':boll,'lower':round(lower,3),'upper':round(upper,3)},
        {'strategy':'DUAL_THRUST','signal':dual,'lower':round(sell,3),'upper':round(buy,3)},
    ]


class OverviewRadar:
    def __init__(self, predictions, histories):
        self.predictions=predictions
        self.histories=histories
        self.public=PublicRadarFeed()
        self.cache=RadarCache()

    def market(self):
        return self.cache.get('market',15,self._market)

    def _market(self):
        feed=self.predictions.market_feed
        reader=getattr(feed,'overview_snapshot',None)
        if reader:
            snapshot=reader()
        else:
            raise ValueError('Bulk market feed not available')
        now=datetime.now(SHANGHAI_TZ)
        items=[]
        for row in snapshot['items']:
            try:
                price=float(row['price']); change=float(row['changePct'])
                observed=datetime.fromisoformat(row['dataTimestamp'])
                if not all(math.isfinite(x) for x in (price,change)) or price<=0 or now-observed>timedelta(days=7) or observed>now+timedelta(minutes=5):
                    continue
            except (ValueError,KeyError,TypeError):
                continue
            root=row['symbol'][:-1]
            meta=CORE_FUTURES_SYMBOLS.get(root+'0',{})
            items.append({**row,'name':meta.get('name',row['name']).removesuffix('主连'),
                'sector':meta.get('sector','其他'),'dataStatus':row.get('dataStatus','CACHED')})
        if not items:
            raise ValueError('No current observed main quotes')
        sectors=[]
        for sector in sorted({i['sector'] for i in items}):
            group=[i for i in items if i['sector']==sector]
            sectors.append({'name':sector,'count':len(group),'up':sum(i['changePct']>0 for i in group),
                'down':sum(i['changePct']<0 for i in group), 'averageChange':round(sum(i['changePct'] for i in group)/len(group),2)})
        items.sort(key=lambda i:i.get('volume',0),reverse=True)
        connected=snapshot.get('connected',True)
        return {'status':'READY' if connected and len(items)==snapshot['catalogCount'] else 'PARTIAL',
            'source':snapshot['source'],'dataTimestamp':max(i['dataTimestamp'] for i in items),
            'connected':connected,'catalogCount':snapshot['catalogCount'],'observedCount':len(items),
            'missingCount':max(0,snapshot['catalogCount']-len(items)),
            'breadth':{'up':sum(i['changePct']>0 for i in items),'down':sum(i['changePct']<0 for i in items),'flat':sum(i['changePct']==0 for i in items)},
            'items':items,'sectors':sectors,
            'message':'每品种取一条主连，热度按成交量（手）排序；涨跌相对各自昨结算，不同品种快照时点可能不同，板块为等权观察。'}

    def news(self):
        result=self.public.news()
        result={**result,'items':[dict(i) for i in result['items']]}
        for item in result['items']:
            text=item['title']+' '+item['summary']
            related=[]
            for symbol,meta in CORE_FUTURES_SYMBOLS.items():
                name=meta['name'].replace('主连','')
                aliases={'黄金':['黄金','沪金'],'白银':['白银','沪银'],'沪铜':['沪铜','铜价'],'豆粕':['豆粕','美豆']}.get(name,[name])
                if any(alias in text for alias in aliases):related.append(symbol[:-1]+'M')
            item['relatedSymbols']=related[:6]
            item['topic']='交易规则' if any(k in text for k in ['交易所','保证金','交割','涨跌停']) else '宏观政策' if any(k in text for k in ['美联储','央行','利率','通胀','关税','财政','赤字','美元','人民币','汇率','货币','国债','美债']) else '海外事件' if any(k in text for k in ['伊朗','以色列','美以','也门','乌克兰','核武','核设施','航母']) else '产业资讯'
        return result

    def signals(self):
        return self.cache.get('signals',60,self._signals)

    def _signals(self):
        scanned=[]; missing=[]; signals=[]; observed_dates=[]
        cutoff=datetime.now(SHANGHAI_TZ)-timedelta(days=7)
        for symbol,meta in CORE_FUTURES_SYMBOLS.items():
            # Only read installed local history here: overview must not trigger
            # dozens of synchronous downloads or block other radar modules.
            if not self.histories.get_metadata(symbol):
                missing.append(symbol);continue
            try:
                bars=self.histories.get_historical_bars(symbol,allow_download=False)
                bars=sorted((b for b in bars if completed_daily_bar(b.timestamp)),key=lambda b:b.timestamp)[-70:]
                if len(bars)<61 or bars[-1].timestamp.replace(tzinfo=bars[-1].timestamp.tzinfo or SHANGHAI_TZ)<cutoff:
                    missing.append(symbol);continue
                rows=strategy_conditions(bars)
                scanned.append(symbol)
                observed_dates.append(bars[-1].timestamp.isoformat())
                for row in rows:
                    if row['signal']=='HOLD':continue
                    b=bars[-1];prev=bars[-2]
                    signals.append({**row,'id':symbol+'-'+row['strategy'],'symbol':symbol[:-1]+'M',
                        'name':meta['name'],'sector':meta['sector'],'close':b.close,
                        'changePct':round((b.close/prev.close-1)*100,2) if prev.close>0 else 0,
                        'dataTimestamp':b.timestamp.isoformat(),'dataStatus':'CACHED','source':self.histories.get_metadata(symbol).get('source','本地日线'),
                        'seriesBasis':'主连已完成日线','reason':dict((s[0],s[2]) for s in STRATEGIES)[row['strategy']]})
            except (ValueError,TypeError,OSError):missing.append(symbol)
        if not scanned:raise ValueError('No completed recent daily histories')
        # Order by recency and symbol, never label signal strength as win rate.
        signals.sort(key=lambda i:(i['dataTimestamp'],i['symbol']),reverse=True)
        groups=[{'id':key,'name':name,'rule':rule,'matched':sum(i['strategy']==key for i in signals),
            'long':sum(i['strategy']==key and i['signal']=='BUY' for i in signals),'short':sum(i['strategy']==key and i['signal']=='SELL' for i in signals)} for key,name,rule in STRATEGIES]
        return {'status':'PARTIAL' if missing else 'READY','source':'已缓存主连日线 · 策略入场条件扫描',
            'dataTimestamp':max(observed_dates),
            'scannedCount':len(scanned),'universeCount':len(CORE_FUTURES_SYMBOLS),'missingCount':len(missing),
            'items':signals,'groups':groups,
            'message':'仅扫描空仓入场条件，不计持仓退出或账户限制；主连换月可能影响阈值，需核验实际合约。条件触发不等于已验证收益或可立即成交。'}

    def read(self,module):
        return {'market':self.market,'news':self.news,'signals':self.signals,'overseas':self.public.overseas}[module]()
