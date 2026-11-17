"""Publish local authorized minute observations for the web replay, without orders."""
from bisect import bisect_right
from datetime import datetime,timezone
import hashlib,json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from data.intraday_replay import SH,load,aggregate,PERIODS
from scripts.fg701_daily_macd import current_contract_daily,daily_macd


def main():
    source=ROOT/'data/history/fg701-intraday-2026-11-17/raw.json'
    raw=json.loads(source.read_text(encoding='utf-8'))
    full_daily=json.loads((ROOT/'data/history/fg701-macd-daily-2026-11-17/raw.json').read_text(encoding='utf-8'))
    current,era=current_contract_daily(full_daily['daily'],raw['spec']['expire_datetime'])
    daily=daily_macd(current,require_listing=False)
    dates=sorted(r['date'] for r in raw['calendar'] if r['trading'])
    bars=[]
    for r in raw['minute']:
        stamp=datetime.fromtimestamp(r['datetime']/1e9,SH)
        if stamp.hour>=18:
            j=bisect_right(dates,stamp.date().isoformat())
            if j>=len(dates):continue
            day=dates[j]
        else:day=stamp.date().isoformat()
        if day>'2026-11-16':continue
        bars.append({'timestamp':stamp.isoformat(),'tradingDate':day,'contract':'FG701','open':r['open'],
                     'high':r['high'],'low':r['low'],'close':r['close'],'volume':int(r['volume']),
                     'openInterest':int(r.get('close_oi') or 0)})
    value={'schemaVersion':1,'symbol':'FG701','providerSymbol':'CZCE.FG701','displayName':'玻璃2701',
           'exchange':'CZCE','source':'天勤TqSdk真实玻璃2701分钟回放','sourceSha256':hashlib.sha256(source.read_bytes()).hexdigest(),
           'generatedAt':datetime.now(timezone.utc).isoformat(),'startDate':'2026-10-19','endDate':'2026-11-16',
           'spec':{'contract':'FG701','volumeMultiple':20,'priceTick':1,'marginPerLot':raw['spec']['margin'],
                   'commissionPerLot':6},'feeAssumption':'模拟手续费每边每手6元起，或账户费率计算值中的较大者；非账户历史实际费率。',
           'bars':bars,'dailyMacd':[d for d in daily if d['date']<='2026-11-16'],'dailyEraAudit':era}
    dest=ROOT/'data/history/intraday-replay/FG701.json';dest.parent.mkdir(parents=True,exist_ok=True)
    if dest.exists():
        existing=json.loads(dest.read_text(encoding='utf-8'))
        if existing['sourceSha256']!=value['sourceSha256']:raise SystemExit('Existing replay archive source differs; preserve it.')
    else:
        temp=dest.with_suffix('.pending');temp.write_text(json.dumps(value,ensure_ascii=False,allow_nan=False),encoding='utf-8');temp.replace(dest)
    verified=load('FG701')
    counts={s:len([b for b in aggregate(verified['bars'],s) if value['startDate']<=b['tradingDate']<=value['endDate']]) for s in PERIODS}
    assert counts=={60:7245,180:2415,300:1449,900:483}
    print(json.dumps({'status':'PUBLISHED','symbol':'FG701','barsByPeriod':counts,'days':21}))


if __name__=='__main__':main()
