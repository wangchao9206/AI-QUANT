"""Exercise actual replay transactions, prefix bounds and concurrent retries.

Creates clearly labelled practice sessions and judgments. --cleanup removes only
this invocation's labelled sessions/notes from the local Docker database, while
retaining immutable analysis runs. Never places an order.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import uuid

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--base-url',default='http://localhost:8088')
parser.add_argument('--cleanup',action='store_true')
parser.add_argument('--output',type=Path)
parser.add_argument('--db-user',default='aiquant')
parser.add_argument('--db-name',default='aiquant')
args=parser.parse_args()
if args.cleanup and urllib.parse.urlsplit(args.base_url).hostname not in ('localhost','127.0.0.1'):
    parser.error('Local fixture cleanup requires a loopback API URL')
base=args.base_url.rstrip('/')+'/api/chanlun/v1/replays'
token=uuid.uuid4().hex
prefix='TEST-REPLAY-'+token
checks=[]
result=None


def call(path='',body=None,expected=200):
    request=urllib.request.Request(base+path,data=json.dumps(body,ensure_ascii=False).encode() if body is not None else None,
                                   headers={'Content-Type':'application/json','Accept':'application/json'})
    try:
        with urllib.request.urlopen(request,timeout=120) as response:
            assert response.status==expected,(response.status,expected)
            assert 'no-store' in response.headers.get('Cache-Control',''),'Replay responses must not be cached'
            return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code!=expected:raise AssertionError((error.code,error.read().decode())) from error
        return {'httpStatus':error.code}


def assert_prefix(value,count):
    analysis=value['analysis']
    assert value['observedBars']==count and analysis['observedBars']==count
    assert len(analysis['bars'])==count and [b['index'] for b in analysis['bars']]==list(range(count))
    assert analysis['observedAsOfDate']==analysis['bars'][-1]['date']
    assert all(s['endIndex']<count and s['firstObservedDate']<=analysis['observedAsOfDate'] for s in analysis['structures'])
    for note in value['decisions']:
        assert note['step']<=value['step'] and note['observedBars']<=count
        snapshot=note['evidence'].get('structureSnapshot')
        if snapshot:assert snapshot['endIndex']<note['observedBars']


def create(kind,count):
    body={'clientRequestId':str(uuid.uuid4()),'title':prefix+'-'+kind,'engineId':'native',
          'datasetId':'fu-daily-2026-10-30','startBars':count}
    value=call(body=body);assert_prefix(value,count)
    repeated=call(body=body)
    assert value['id']==repeated['id'] and repeated['step']==0
    call(body={**body,'startBars':count-1},expected=409)
    return value


def decision(value,content):
    selected=next((s for s in reversed(value['analysis']['structures']) if s['type']=='BI'),None)
    return {'clientRequestId':str(uuid.uuid4()),'expectedStep':value['step'],
            'structureId':selected['id'] if selected else None,'outlook':'WAIT','content':content,'lessonNumber':62}


try:
    initial=create('main',100);identifier=initial['id'];path='/'+identifier
    advance0={'clientRequestId':str(uuid.uuid4()),'expectedStep':0}
    call(path+'/advance',advance0,expected=409)
    assert_prefix(call(path),100);checks.append('advance_requires_saved_decision')
    first=decision(initial,prefix+'：记录当时结构与失效条件，不作交易判断。')
    with ThreadPoolExecutor(max_workers=2) as pool:
        saved=list(pool.map(lambda _:call(path+'/decisions',first),range(2)))
    assert all(v['decisionSubmitted'] and len(v['decisions'])==1 for v in saved)
    assert saved[0]['decisions'][0]['id']==saved[1]['decisions'][0]['id']
    call(path+'/decisions',{**first,'content':'changed'},expected=409)
    call(path+'/decisions',{**first,'clientRequestId':str(uuid.uuid4())},expected=409)
    checks.append('concurrent_identical_decisions_idempotent_and_immutable')
    with ThreadPoolExecutor(max_workers=2) as pool:
        advanced=list(pool.map(lambda _:call(path+'/advance',advance0),range(2)))
    assert all(v['step']<=1 for v in advanced)
    current=call(path);assert_prefix(current,101);assert current['step']==1
    assert call(path+'/advance',advance0)['step']==1
    call(path+'/advance',{'clientRequestId':str(uuid.uuid4()),'expectedStep':0},expected=409)
    call(path+'/advance',{'clientRequestId':str(uuid.uuid4()),'expectedStep':1},expected=409)
    checks.append('concurrent_identical_advance_reveals_one_bar_only')
    second=decision(current,prefix+'：第二步保持独立记录。')
    call(path+'/decisions',second)
    commands=[{'clientRequestId':str(uuid.uuid4()),'expectedStep':1} for _ in range(2)]
    def compete(command):
        try:return call(path+'/advance',command)
        except AssertionError as failure:
            if failure.args and failure.args[0][0]==409:return {'httpStatus':409}
            raise
    with ThreadPoolExecutor(max_workers=2) as pool:competing=list(pool.map(compete,commands))
    assert sum(v.get('httpStatus')==409 for v in competing)==1,competing
    current=call(path);assert_prefix(current,102);assert current['step']==2
    call(path+'/decisions',first)
    source=next(d for d in current['decisions'] if d['step']==0)
    assert source['content']==first['content'] and source['observedBars']==100
    assert source['evidence']['replaySessionId']==identifier and source['evidence']['lessonNumber']==62
    assert source['evidence']['profileHash']==initial['analysis']['profileHash']
    assert not current['decisionSubmitted']
    checks.append('competing_commands_do_not_skip_steps_and_restore_preserves_original_evidence')
    tail=create('end',1893);tail_path='/'+tail['id']
    tail=call(tail_path+'/decisions',decision(tail,prefix+'：末端边界验收。'))
    tail=call(tail_path+'/advance',{'clientRequestId':str(uuid.uuid4()),'expectedStep':0})
    assert_prefix(tail,1894);assert tail['status']=='COMPLETE'
    call(tail_path+'/advance',{'clientRequestId':str(uuid.uuid4()),'expectedStep':1},expected=409)
    checks.append('final_bar_completes_without_reading_past_dataset_end')
    result={'status':'PASSED','checks':checks,'mainSession':identifier,'terminalSession':tail['id'],
            'profileHash':initial['analysis']['profileHash'],'cleanupRequested':args.cleanup}
finally:
    if args.cleanup:
        # Only this random invocation prefix is eligible; no existing session,
        # user judgment, immutable run, or external trading data is deleted.
        sql=f"""begin;
        create temporary table owned_replays on commit drop as select id from chanlun.replay_session where title like '{prefix}-%';
        create temporary table owned_notes on commit drop as select judgment_id from chanlun.replay_decision where session_id in (select id from owned_replays);
        delete from chanlun.replay_advance where session_id in (select id from owned_replays);
        delete from chanlun.replay_decision where session_id in (select id from owned_replays);
        delete from chanlun.replay_session where id in (select id from owned_replays);
        delete from chanlun.judgment where id in (select judgment_id from owned_notes) and evidence->>'replaySessionId' in (select id::text from owned_replays);
        commit;"""
        subprocess.run(['docker','compose','-f',str(Path(__file__).resolve().parents[1]/'infrastructure/docker-compose.yml'),
                        'exec','-T','postgres','psql','-U',args.db_user,'-d',args.db_name,'-v','ON_ERROR_STOP=1','-c',sql],check=True)

if result is not None:
    result['cleanupCompleted']=args.cleanup
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
