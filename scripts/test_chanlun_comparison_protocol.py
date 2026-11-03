"""Replay real archived engine events through isolated Java/PostgreSQL.

Reads only the named source runs from the running system. All comparison and
judgment mutations stay in an isolated disposable database, including <50-bar
derived prefixes. No engine workers, market connection, or orders are needed.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request
import uuid


DEFAULT_RUNS=['8f9709f0-b83a-4f6c-a490-2925c85c1f70','7fd5cf1c-afdd-4f65-8653-cd7440489452','af095865-2ffd-4071-aa90-cac3c7b21135']


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path);p.add_argument('--runs',nargs='+',default=DEFAULT_RUNS);args=p.parse_args()
    ids=[str(uuid.UUID(value)) for value in args.runs]
    token=uuid.uuid4().hex[:10];network='aiquant-compare-verify-'+token;db=network+'-db';java=network+'-java';client=network+'-client';created=[];report=None
    def docker(*parts,input=None):
        return subprocess.run(['docker',*parts],input=input,check=True,capture_output=True,text=True,encoding='utf-8').stdout.strip()
    def read_json(url):
        with urllib.request.urlopen(url,timeout=120) as response:return json.load(response)
    originals={id:read_json('http://localhost:8088/api/chanlun/v1/runs/'+id+'/structures') for id in ids}
    source_events={}
    for id in ids:
        raw=docker('compose','-f','infrastructure/docker-compose.yml','exec','-T','postgres','psql','-U','aiquant','-d','aiquant','-At','-c',f"select coalesce(jsonb_agg(payload order by event_seq),'[]'::jsonb) from chanlun.structure_event where run_id='{id}'")
        source_events[id]=json.loads(raw)
        assert source_events[id],('Missing archived events',id)
    def quoted(value):return "'"+json.dumps(value,ensure_ascii=False).replace("'","''")+"'::jsonb"
    try:
        docker('network','create','--internal',network)
        docker('run','-d','--name',db,'--network',network,'--network-alias','db','-e','POSTGRES_DB=aiquant','-e','POSTGRES_USER=aiquant','-e','POSTGRES_PASSWORD=isolated-fixture-only','postgres:17.6-alpine3.22');created.append(db)
        for _ in range(45):
            try:docker('exec',db,'pg_isready','-h','127.0.0.1','-U','aiquant','-d','aiquant');break
            except subprocess.CalledProcessError:time.sleep(1)
        docker('run','-d','--name',java,'--network',network,'--network-alias','java','-e','DATABASE_URL=jdbc:postgresql://db:5432/aiquant','-e','DATABASE_USERNAME=aiquant','-e','DATABASE_PASSWORD=isolated-fixture-only','ai-quant-chanlun-service');created.append(java)
        docker('run','-d','--name',client,'--network',network,'--read-only','--tmpfs','/tmp','--entrypoint','python','ai-quant-algorithm-service','-m','http.server','8000');created.append(client)
        bridge="""import json,sys,urllib.request,urllib.error
url,body,expected=sys.argv[1:];req=urllib.request.Request(url,data=None if body=='null' else body.encode(),headers={'Content-Type':'application/json'})
try:
 r=urllib.request.urlopen(req,timeout=110);code=r.status;data=r.read()
except urllib.error.HTTPError as e:code=e.code;data=e.read()
assert code==int(expected),(code,data.decode());print(data.decode())
"""
        def call(path,body=None,status=200):
            raw=docker('exec',client,'python','-c',bridge,'http://java:8084/api/chanlun/v1'+path,json.dumps(body),str(status))
            return json.loads(raw) if raw else None
        for _ in range(70):
            try:call('/comparisons');break
            except (OSError,AssertionError,subprocess.CalledProcessError):time.sleep(1)
        else:raise RuntimeError('Isolated Java did not become ready')
        statements=['begin;']
        for id,result in originals.items():
            assert result['engineId'] in ('native','chanpy','czsc','baseline')
            dataset=result['datasetId'];assert dataset=='fu-daily-2026-10-30'
            statements.append(f"insert into chanlun.analysis_run(id,client_request_id,engine_id,dataset_id,observed_bars,status,result) values('{id}','{id}','{result['engineId']}','{dataset}',{int(result['observedBars'])},'SUCCEEDED',{quoted(result)});")
            for e in source_events[id]:
                assert len(e['id'])==24 and all(c in '0123456789abcdef' for c in e['id'])
                statements.append(f"insert into chanlun.structure_event(run_id,event_seq,structure_id,payload) values('{id}',{int(e['eventSeq'])},'{e['id']}',{quoted(e)});")
        statements.append('commit;')
        docker('exec','-i',db,'psql','-U','aiquant','-d','aiquant','-v','ON_ERROR_STOP=1',input='\n'.join(statements))
        body={'clientRequestId':str(uuid.uuid4()),'runIds':ids,'layer':'BI','projection':'WITH_CONFIRMATION','confirmedOnly':False}
        run=call('/comparisons',body);assert run['status']=='SUCCEEDED',run
        id=run['id'];r=run['report'];assert r['firstDifference'] and r['firstGeometryDifference']
        assert call('/comparisons',body)['report']==r==call('/comparisons/'+id)['report']
        call('/comparisons',{**body,'layer':'ZONE'},409)
        checks=['real_archived_sources_compared_without_workers','create_get_idempotence_and_changed_payload_conflict']
        index=r['firstDifference']['observedIndex'];assert index+1<50,(index,'Expected a real early difference to cover derived prefixes')
        detail=call(f'/comparisons/{id}/at/{index}')
        chosen=next(f for f in detail['frames'] if f['analysis']['structures'])
        for f in detail['frames']:
            a=f['analysis'];source=f['sourceRunId'];assert len(a['bars'])==a['observedBars']==index+1
            assert a['bars']==originals[source]['bars'][:index+1]
            state={}
            for event in source_events[source]:
                if event['observedDate']>detail['date']:break
                if event['eventType']=='RETRACTED':state.pop(event['id'],None)
                else:state[event['id']]=event
            assert {s['id']:s['revision'] for s in a['structures']}=={key:s['revision'] for key,s in state.items()}
            assert all(s['endIndex']<=index for s in a['structures'])
        call(f'/comparisons/{id}/at/{r["observedBars"]}',status=400)
        checks.append('first_difference_uses_early_observation_prefix_not_final_geometry')
        structure=chosen['analysis']['structures'][0]
        events=call(f'/comparisons/{id}/events?sourceRunId={chosen["sourceRunId"]}&observedIndex={index}&structureId={structure["id"]}')
        assert events and all(e['observedDate']<=detail['date'] for e in events)
        call(f'/comparisons/{id}/events?sourceRunId={uuid.uuid4()}&observedIndex={index}&structureId={structure["id"]}',status=400)
        checks.append('event_queries_are_member_and_observation_bounded')
        note={'clientRequestId':str(uuid.uuid4()),'sourceRunId':chosen['sourceRunId'],'structureId':structure['id'],'outlook':'WAIT','content':'ISOLATED_COMPARISON_PREFIX_REVIEW','lessonNumber':62}
        saved=call(f'/comparisons/{id}/at/{index}/judgments',note)
        assert call(f'/comparisons/{id}/at/{index}/judgments',note)['id']==saved['id']
        call(f'/comparisons/{id}/at/{index}/judgments',{**note,'content':'changed'},409)
        row=next(n for n in call('/judgments') if n['id']==saved['id'])
        assert row['evidence']['comparisonId']==id and row['evidence']['observedIndex']==index
        prefix=call('/runs/'+row['runId']+'/structures')
        assert prefix['observedBars']==index+1 and prefix['bars']==chosen['analysis']['bars'] and prefix['structures']==chosen['analysis']['structures']
        assert prefix['derivedFrom']['sourceRunId']==chosen['sourceRunId']
        future=next(s for s in originals[chosen['sourceRunId']]['structures'] if s['id'] not in {s['id'] for s in prefix['structures']})
        call(f'/comparisons/{id}/at/{index}/judgments',{**note,'clientRequestId':str(uuid.uuid4()),'structureId':future['id']},400)
        checks.append('immutable_under_50_bar_judgment_materialization_retry_conflict_and_future_object_rejection')
        blank=call(f'/comparisons/{id}/at/0');assert all(not f['analysis']['structures'] for f in blank['frames'])
        zero_note={**note,'clientRequestId':str(uuid.uuid4()),'structureId':None}
        first=call(f'/comparisons/{id}/at/0/judgments',zero_note)
        zero=next(n for n in call('/judgments') if n['id']==first['id'])
        assert call('/runs/'+zero['runId']+'/structures')['observedBars']==1
        checks.append('one_bar_empty_state_can_be_archived_without_worker_recalculation')
        call('/comparisons',{**body,'clientRequestId':str(uuid.uuid4()),'layer':'SEGMENT'},400)
        call('/comparisons',{**body,'clientRequestId':str(uuid.uuid4()),'layer':'ZONE','confirmedOnly':True},400)
        call('/comparisons',{**body,'clientRequestId':str(uuid.uuid4()),'runIds':[ids[0],ids[0]]},400)
        checks.append('unsupported_layers_unknown_confirmation_and_duplicate_engine_rejected')
        docker('restart',java)
        for _ in range(70):
            try:
                assert call('/comparisons/'+id)['report']==r;break
            except (OSError,AssertionError,subprocess.CalledProcessError):time.sleep(1)
        else:raise RuntimeError('Archive did not recover after restart')
        assert call(f'/comparisons/{id}/at/{index}')==detail
        assert any(n['id']==saved['id'] for n in call('/judgments'))
        checks.append('restart_restores_report_prefix_and_judgment_without_workers')
        report={'status':'PASS','verifiedAt':datetime.now(timezone.utc).isoformat(),'scope':'ISOLATED_JAVA_POSTGRES_REAL_FROZEN_ENGINE_EVENTS_NO_WORKERS','sourceRunIds':ids,'firstDifference':{'index':index,'date':detail['date'],'bars':index+1},'checks':checks,'cleanupCompleted':False}
    except Exception:
        if java in created:
            result=subprocess.run(['docker','logs','--tail','55',java],capture_output=True,text=True,encoding='utf-8');print(result.stdout);print(result.stderr)
        raise
    finally:
        for name in reversed(created):docker('rm','-f',name)
        docker('network','rm',network)
        if report:report['cleanupCompleted']=True
    if args.output:args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
