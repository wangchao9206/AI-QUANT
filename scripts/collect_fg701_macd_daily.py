"""Read-only FG701 provider serial; separate reused delivery eras before MACD."""
from __future__ import annotations

import argparse
import contextlib
from datetime import datetime,timezone
import hashlib
import io
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.collect_fg701_minutes import credentials,records,write_json


def collect(out,timeout):
    from tqsdk import TqApi,TqAuth,TqSim
    import tqsdk
    user,password=credentials()
    api=None
    try:
        api=TqApi(TqSim(),auth=TqAuth(user,password),web_gui=False,debug=False,disable_print=True)
        serial=api.get_kline_serial('CZCE.FG701',86400,data_length=10000)
        deadline=time.time()+timeout
        while not api.is_serial_ready(serial):
            if time.time()>=deadline:
                raise TimeoutError('SERIAL_TIMEOUT')
            api.wait_update(deadline=min(deadline,time.time()+2))
        daily=records(serial.copy())
        if not daily or daily[0]['id']!=0:
            raise ValueError('Daily series does not start at listing ID zero')
        if any(b['id']!=a['id']+1 or b['datetime']<=a['datetime'] for a,b in zip(daily,daily[1:])):
            raise ValueError('Daily source IDs/timestamps are not contiguous')
        payload={'symbol':'CZCE.FG701','source':'Authenticated TqSdk provider daily serial; historical code reuse requires era separation',
                 'sdkVersion':tqsdk.__version__,'capturedAt':datetime.now(timezone.utc).isoformat(),
                 'daily':daily,'lastDailyProvisional':True}
        path=out/'raw.json'
        write_json(path,payload)
        return {'status':'COLLECTED','symbol':'CZCE.FG701','dailyBars':len(daily),
                'firstId':daily[0]['id'],'lastId':daily[-1]['id'],
                'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    finally:
        if api is not None:
            api.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=ROOT/'data/history/fg701-macd-daily-2026-11-17')
    parser.add_argument('--timeout',type=int,default=90)
    args=parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    if (args.out/'raw.json').exists():
        print(json.dumps({'status':'EXISTING_PRESERVED'}))
        return
    with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
        try:
            result=collect(args.out,args.timeout)
        except Exception as exc:
            result={'status':'UNAVAILABLE','errorType':type(exc).__name__}
    write_json(args.out/'collection.json',result)
    print(json.dumps(result,ensure_ascii=True),flush=True)
    if result['status']!='COLLECTED':
        raise SystemExit(1)


if __name__=='__main__':
    main()
