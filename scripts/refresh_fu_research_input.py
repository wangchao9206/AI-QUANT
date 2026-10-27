#!/usr/bin/env python3
"""Refresh an isolated FU research input via the existing authenticated data service.

No credential is printed, no production cache is replaced, no order is submitted.
"""
import argparse,base64,contextlib,io,json,subprocess,sys,tempfile,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from data.tqsdk_backtest import TqSdkBacktestDataProvider
from data.trading_day import completed_daily_bar
from backtesting.independent_research import causal_prices

WORKER="""
import base64,contextlib,io,json,re,signal,tempfile,shutil
from pathlib import Path
from datetime import date
def deadline(*_):raise TimeoutError('deadline')
signal.signal(signal.SIGALRM,deadline);signal.alarm(150)
cache=Path(tempfile.mkdtemp(prefix='fu_research_refresh_'))
result={}
with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
 try:
  from data.tqsdk_backtest import TqSdkBacktestDataProvider
  provider=TqSdkBacktestDataProvider(cache_dir=cache)
  ds=provider.load('FU0','KQ.m@SHFE.fu',n=2500,force_download=True,start_date=date(2019,1,1))
  raw=provider._cache_path('FU0',date(2019,1,1),None).read_bytes()
  result={'status':'READY','rawBase64':base64.b64encode(raw).decode()}
 except Exception as error:
  result={'status':'UNAVAILABLE','errorType':type(error).__name__}
 finally:
  signal.alarm(0)
  for item in cache.iterdir():
   if item.is_file():item.unlink()
  cache.rmdir()
print(json.dumps(result))
"""

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--container',default='ai-quant-algorithm-service-1')
    parser.add_argument('--output',default='.test-tmp/fu-latest-audited.json')
    args=parser.parse_args();output=ROOT/args.output
    result=subprocess.run(['docker','exec','-i','-e','PYTHONPATH=/app',args.container,'python','-'],
                          input=WORKER.encode(),capture_output=True,timeout=180)
    if result.returncode:raise SystemExit('Research data query failed; production cache and accounts unchanged.')
    response=json.loads(result.stdout)
    if response.get('status')!='READY':raise SystemExit('Research data unavailable: '+response.get('errorType','Unknown'))
    raw=base64.b64decode(response['rawBase64'],validate=True)
    output.parent.mkdir(parents=True,exist_ok=True)
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent,delete=False,suffix='.json') as stream:
            temporary=Path(stream.name);stream.write(raw)
        ds=TqSdkBacktestDataProvider(cache_dir=ROOT/'.test-tmp')._read_cache(temporary,0,allow_stale=True)
        if ds is None or ds.symbol!='FU0' or any(not completed_daily_bar(b.timestamp) for b in ds.bars):
            raise ValueError('Completed FU delivery observations required')
        causal_prices(ds)
        os.replace(temporary,output);temporary=None
        print(json.dumps({'status':'AUDITED','symbol':'FU0','bars':len(ds.bars),
            'first':str(ds.bars[0].timestamp.date()),'last':str(ds.bars[-1].timestamp.date()),
            'output':str(output),'productionCacheChanged':False,'ordersSubmitted':0}))
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)
if __name__=='__main__':main()
