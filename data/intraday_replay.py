"""Validated local minute archives; only completed candles at the requested clock."""
from __future__ import annotations

from collections import Counter,defaultdict
from datetime import date,datetime,timedelta
from functools import lru_cache
import json
import math
import os
from pathlib import Path
import re
from zoneinfo import ZoneInfo

SH=ZoneInfo('Asia/Shanghai')
PERIODS=(60,180,300,900)
SYMBOL=re.compile(r'^[A-Z]{1,4}[0-9]{3,4}$')


def archive_root():
    return Path(os.getenv('HISTORY_CACHE_DIR','data/history'))/'intraday-replay'


@lru_cache(maxsize=16)
def _read(path:str,mtime:int,size:int):
    value=json.loads(Path(path).read_text(encoding='utf-8'))
    if value.get('schemaVersion')!=1 or not SYMBOL.fullmatch(value.get('symbol','')):
        raise ValueError('分钟档案格式或合约无效')
    previous=None
    for b in value.get('bars',[]):
        stamp=datetime.fromisoformat(b['timestamp'])
        if stamp.tzinfo is None or previous is not None and stamp<=previous:
            raise ValueError('分钟档案时间顺序无效')
        previous=stamp
        numbers=[b.get(k) for k in ('open','high','low','close','volume')]
        if any(n is None or not math.isfinite(n) for n in numbers):
            raise ValueError('分钟档案存在无效数值')
        o,h,l,c,v=numbers
        if min(o,h,l,c)<=0 or v<0 or l>min(o,c) or h<max(o,c):
            raise ValueError('分钟档案价格或成交量无效')
        date.fromisoformat(b['tradingDate'])
    if not value.get('bars') or len(value.get('sourceSha256',''))!=64:
        raise ValueError('分钟档案缺少真实来源或行情')
    spec=value.get('spec',{})
    if spec.get('contract')!=value['symbol'] or any(not math.isfinite(spec.get(k,0)) or spec.get(k,0)<=0 for k in ('volumeMultiple','priceTick','marginPerLot')) or spec.get('commissionPerLot',-1)<0:
        raise ValueError('分钟档案缺少合约规格')
    return value


def load(symbol:str):
    symbol=symbol.strip().upper()
    if not SYMBOL.fullmatch(symbol):
        raise ValueError('分钟回放必须选择实际交割合约')
    path=archive_root()/(symbol+'.json')
    if not path.is_file():
        raise ValueError('所选合约暂无已核验的分钟回放档案')
    stat=path.stat()
    value=_read(str(path.resolve()),stat.st_mtime_ns,stat.st_size)
    if value['symbol']!=symbol:
        raise ValueError('分钟档案合约不匹配')
    return value


def aggregate(bars,seconds):
    if seconds not in PERIODS:
        raise ValueError('分钟回放支持1、3、5、15分钟')
    groups=defaultdict(list)
    for b in bars:
        stamp=datetime.fromisoformat(b['timestamp'])
        bucket=int(stamp.timestamp())//seconds*seconds
        groups[(b['tradingDate'],bucket)].append(b)
    result=[]
    for (day,bucket),rows in sorted(groups.items(),key=lambda p:p[0][1]):
        times=[int(datetime.fromisoformat(b['timestamp']).timestamp()) for b in rows]
        if times!=list(range(bucket,bucket+seconds,60)):
            # Never fabricate a partial or gapped aggregate candle.
            continue
        result.append({'timestamp':datetime.fromtimestamp(bucket,SH).isoformat(),'tradingDate':day,
                       'contract':rows[0]['contract'],'open':rows[0]['open'],'high':max(b['high'] for b in rows),
                       'low':min(b['low'] for b in rows),'close':rows[-1]['close'],
                       'volume':sum(b['volume'] for b in rows),'openInterest':rows[-1].get('openInterest',0)})
    return result


def wire(bar):
    return {k:bar[k] for k in ('timestamp','contract','open','high','low','close','volume','openInterest')}


def catalog():
    symbols=[]
    errors=[]
    for path in sorted(archive_root().glob('*.json')):
        try:
            a=load(path.stem)
            visible=[b for b in a['bars'] if a['startDate']<=b['tradingDate']<=a['endDate']]
            symbols.append({'symbol':a['symbol'],'name':a.get('displayName',a['symbol']),'displayName':a.get('displayName',a['symbol']),
                            'exchange':a.get('exchange',''),'sector':'分时回放','startDate':a['startDate'],'endDate':a['endDate'],
                            'totalBars':len(visible),'periods':list(PERIODS),'source':a['source']})
        except (ValueError,KeyError,OSError,json.JSONDecodeError):
            errors.append(path.stem)
    return {'symbols':symbols,'periods':list(PERIODS),'unavailable':errors,'source':'已核验真实分钟档案'}


def history(symbol,seconds,start_date=None,end_date=None):
    a=load(symbol)
    start=start_date.isoformat() if isinstance(start_date,date) else start_date or a['startDate']
    end=end_date.isoformat() if isinstance(end_date,date) else end_date or a['endDate']
    if not a['startDate']<=start<=end<=a['endDate']:
        raise ValueError('回放日期必须位于已核验档案范围内')
    rows=aggregate(a['bars'],seconds)
    selected=[b for b in rows if start<=b['tradingDate']<=end]
    if len(selected)<2:
        raise ValueError('所选区间不足两根完整分钟K线')
    first=selected[0]['timestamp']
    context=[wire(b) for b in rows if b['timestamp']<first][-600:]
    counts=Counter(b['tradingDate'] for b in a['bars'])
    full_count=Counter(counts.values()).most_common(1)[0][0]
    complete_days=[day for day,count in counts.items() if count==full_count and any(
        b['tradingDate']==day and datetime.fromisoformat(b['timestamp']).astimezone(SH).strftime('%H:%M')=='14:59' for b in a['bars'])]
    return {'symbol':a['symbol'],'providerSymbol':a['providerSymbol'],'source':a['source'],
            'generatedAt':a['generatedAt'],'bars':[wire(b) for b in selected],
            'rollEvents':[],'contractSpecs':{a['symbol']:a['spec']},'signalBars':[],'contextBars':context,
            'replayContext':{'barSeconds':seconds,'sourceSha256':a['sourceSha256'],'dailyMacd':a.get('dailyMacd',[]),
                             'minuteBars':a['bars'],'completeTradingDates':complete_days,
                             'feeAssumption':a.get('feeAssumption','每边手续费取档案与账户费率计算值的较大者')}}


def chart(symbol,seconds,as_of,limit=240):
    if as_of.tzinfo is None:
        raise ValueError('回放时点必须包含时区')
    a=load(symbol)
    rows=aggregate(a['bars'],seconds)
    visible=[wire(b) for b in rows if datetime.fromisoformat(b['timestamp'])+timedelta(seconds=seconds)<=as_of]
    known=[d for d in a.get('dailyMacd',[]) if datetime.fromisoformat(d['availableAt'])<=as_of]
    return {'source':a['source'],'asOf':as_of,'bars':visible[-limit:],
            'dailyContext':known[-1] if known else None,'barSeconds':seconds}
