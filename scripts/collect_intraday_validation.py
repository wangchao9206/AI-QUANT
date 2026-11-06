"""Bounded read-only primary data collection in a separate SDK process; no orders."""
import hashlib,json,math,os,time,statistics
from datetime import datetime,timezone
from pathlib import Path
from tqsdk import TqApi,TqAuth,TqSim
from data.intraday_feed import observed_bars

ROOTS=['KQ.m@SHFE.rb','KQ.m@SHFE.cu','KQ.m@SHFE.au','KQ.m@DCE.m','KQ.m@DCE.i','KQ.m@CZCE.TA','KQ.m@CFFEX.IF','KQ.m@SHFE.fu']
if os.getenv('RESEARCH_ROOTS_JSON'):ROOTS=json.loads(os.environ['RESEARCH_ROOTS_JSON'])
minimum_volume=int(os.getenv('ACTIVE_MIN_MEDIAN_DAILY_VOLUME','0'))
OUT=Path('/study');OUT.mkdir(parents=True,exist_ok=True)
if (OUT/'collection.json').exists():raise SystemExit('Existing collection preserved; mount a new empty study directory.')
def write(name,value):
    path=OUT/name;temp=path.with_suffix('.pending');temp.write_text(json.dumps(value,ensure_ascii=False,allow_nan=False),encoding='utf-8');temp.replace(path)
report={'startedAt':datetime.now(timezone.utc).isoformat(),'selection':'Eight fixed cross-market roots; current active contracts, not historical investible universe.',
    'sdkMode':'TqSim read-only collection; no order methods invoked','requestedBarsPerSerial':8000,'activityMinimumMedianDailyVolume20':minimum_volume,'results':[]}
write('collection.json',report)
api=None
try:
    api=TqApi(TqSim(),auth=TqAuth(os.environ['TQSDK_USERNAME'],os.environ['TQSDK_PASSWORD']),web_gui=False)
    for root in ROOTS:
        item={'root':root}
        try:
            main=api.get_quote(root);deadline=time.time()+30
            while not main.underlying_symbol and time.time()<deadline:api.wait_update(deadline=time.time()+1)
            contract=main.underlying_symbol
            if not contract:raise ValueError('No current actual contract')
            quote=api.get_quote(contract)
            minute=api.get_kline_serial(contract,900,data_length=8000)
            daily=api.get_kline_serial(contract,86400,data_length=8000)
            deadline=time.time()+30
            while (not api.is_serial_ready(minute) or not api.is_serial_ready(daily)) and time.time()<deadline:api.wait_update(deadline=time.time()+1)
            m=observed_bars(minute);d=observed_bars(daily)
            if len(m)<100 or len(d)<21:raise ValueError('Insufficient primary history')
            median_volume=statistics.median(b['volume'] for b in d[-21:-1])
            item['medianCompleteDailyVolume20']=median_volume
            if median_volume<minimum_volume:
                item.update(status='INACTIVE',reason='Below frozen activity threshold');report['results'].append(item);write('collection.json',report);continue
            tick=float(quote.price_tick);multiple=int(quote.volume_multiple)
            if not math.isfinite(tick) or tick<=0 or multiple<=0:raise ValueError('Missing actual contract specification')
            value={'root':root,'contract':contract,'capturedAt':datetime.now(timezone.utc).isoformat(),'source':'TqSdk primary actual delivery contract',
                'priceTick':tick,'volumeMultiple':multiple,'bars15m':m,'barsDaily':d,'lastBarsProvisional':True}
            name=root.split('.')[-1]+'-15m.json';write(name,value)
            item.update(status='COLLECTED',contract=contract,bars15m=len(m),barsDaily=len(d),start=m[0]['timestamp'],end=m[-1]['timestamp'],file=name,sha256=hashlib.sha256((OUT/name).read_bytes()).hexdigest())
        except Exception as error:item.update(status='UNAVAILABLE',errorType=type(error).__name__)
        report['results'].append(item);write('collection.json',report)
except Exception as error:report['fatalErrorType']=type(error).__name__
finally:
    if api is not None:api.close()
    report['finishedAt']=datetime.now(timezone.utc).isoformat();write('collection.json',report)
print(json.dumps({'collected':sum(r['status']=='COLLECTED' for r in report['results']),'attempted':len(report['results']),'fatalErrorType':report.get('fatalErrorType')},ensure_ascii=True))
