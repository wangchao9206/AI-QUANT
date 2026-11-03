"""Bounded LOCAL capacity check on real CLOSED-market shared FU MIN5 input.

Creates seven exact-owned tasks alongside the known default, measures cold
bootstrap and warm checks, verifies the eight-task limit, then cleans only its
own tasks. This is NOT eight independent markets or open-market throughput.
"""
import argparse
from datetime import datetime,timezone
import json
import math
from pathlib import Path
import statistics
import subprocess
import time
import urllib.error
import urllib.request
import uuid

DEFAULT_MONITOR='0744473b-c46c-4f42-a95a-5ef97961c231'


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    base='http://localhost:8088/api/chanlun/v1/monitors';prefix='TEST-CAPACITY-'+uuid.uuid4().hex;owned=[];keys=[];report=None
    def call(path='',body=None,status=200):
        req=urllib.request.Request(base+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req,timeout=120) as r:assert r.status==status;return json.load(r)
        except urllib.error.HTTPError as exc:
            if exc.code!=status:raise AssertionError((exc.code,exc.read().decode())) from exc
            return None
    def docker(*parts):return subprocess.run(['docker',*parts],check=True,capture_output=True,text=True,encoding='utf-8').stdout.strip()
    def distribution(values):
        ordered=sorted(values)
        return {'n':len(values),'minSeconds':min(values),'medianSeconds':statistics.median(values),'p95NearestRankSeconds':ordered[math.ceil(.95*len(ordered))-1],'maxSeconds':max(values)}
    try:
        active=[r for r in call() if r['enabled']]
        if len(active)!=1 or active[0]['id']!=DEFAULT_MONITOR:raise RuntimeError('Controlled run requires ONLY the known default enabled; no existing user task will be changed')
        original=call('/'+DEFAULT_MONITOR)
        if original['status']!='CLOSED' or original['symbol']!='FU2701' or original['frequency']!='MIN5':raise RuntimeError('This benchmark is restricted to the known closed-market FU MIN5 workload')
        cold=[]
        for i in range(7):
            key=str(uuid.uuid4());keys.append(key);started=time.perf_counter()
            value=call(body={'clientRequestId':key,'title':prefix+'-'+str(i),'symbol':'FU2701','frequency':'MIN5'})
            identifier=value['id'];owned.append(identifier)
            for _ in range(60):
                value=call('/'+identifier+'/check',{})
                if value['observedBars']:break
                time.sleep(.25)
            cold.append(time.perf_counter()-started)
            assert value['observedBars']==original['observedBars'] and value['status']=='CLOSED'
            assert all(e['inboxState']=='SUPPRESSED_BOOTSTRAP' for e in value['events'])
        assert len([r for r in call() if r['enabled']])==8
        call(body={'clientRequestId':str(uuid.uuid4()),'title':prefix+'-ninth','symbol':'FU2701','frequency':'MIN5'},status=409)
        warm=[];cycles=[]
        for _ in range(3):
            cycle=time.perf_counter()
            for identifier in [DEFAULT_MONITOR,*owned]:
                started=time.perf_counter();value=call('/'+identifier+'/check',{});warm.append(time.perf_counter()-started)
                assert value['status']=='CLOSED' and value['observedBars']==original['observedBars']
            cycles.append(time.perf_counter()-cycle)
        after=call('/'+DEFAULT_MONITOR)
        assert after['profileHash']==original['profileHash'] and after['events']==original['events']
        limits={name:json.loads(docker('inspect','--format','{{json .HostConfig}}','ai-quant-'+name+'-1')) for name in ('chanlun-service','algorithm-service')}
        report={'status':'PASS','verifiedAt':datetime.now(timezone.utc).isoformat(),'scope':'REAL_LOCAL_CLOSED_MARKET_EIGHT_LOGICAL_TASKS_ONE_SHARED_PRIMARY_SERIAL',
            'symbol':'FU2701','frequency':'MIN5','barsPerTask':original['observedBars'],'logicalTasks':8,'primarySubscriptionCombinations':1,
            'inputHash':original['analysis']['inputHash'],'profileHash':original['profileHash'],
            'firstProviderIndex':original['analysis']['bars'][0]['providerIndex'],'lastProviderIndex':original['analysis']['bars'][-1]['providerIndex'],
            'coldBootstrap':distribution(cold),'warmUnchangedChecks':distribution(warm),'eightTaskWarmCycle':distribution(cycles),
            'containerLimits':{k:{'cpuNano':v['NanoCpus'],'memoryBytes':v['Memory']} for k,v in limits.items()},
            'images':{name:docker('inspect','--format','{{.Image}}','ai-quant-'+name+'-1') for name in ('chanlun-service','algorithm-service')},
            'checks':['eight_enabled_limit_ninth_rejected','cold_bootstrap_no_fresh_alerts','warm_checks_preserve_watermarks','default_task_events_unchanged'],
            'limitations':['One shared live-provider serial, closed market; not eight independent subscriptions.','Warm input does not change; not the cost of eight simultaneous newly sealed bars.','Shared host and other application background work are uncontrolled.','Endpoint timing includes gateway/Java/worker/DB/JSON and local transfer; no browser render or competitor measurement.'],
            'ownedTasks':owned,'cleanupCompleted':False}
    finally:
        for identifier in owned:call('/'+identifier+'/control',{'enabled':False})
        if keys:
            ids=','.join("'"+str(uuid.UUID(k))+"'" for k in keys)
            target=f"select id from chanlun.monitor where client_request_id in ({ids}) and title like '{prefix}%'"
            sql=f"begin; delete from chanlun.monitor_review where monitor_id in ({target}); update chanlun.monitor set latest_snapshot_id=null where id in ({target}); delete from chanlun.monitor_event where monitor_id in ({target}); delete from chanlun.monitor_snapshot where monitor_id in ({target}); delete from chanlun.monitor where id in ({target});commit;"
            docker('compose','-f','infrastructure/docker-compose.yml','exec','-T','postgres','psql','-U','aiquant','-d','aiquant','-v','ON_ERROR_STOP=1','-c',sql)
        if report:report['cleanupCompleted']=True
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
