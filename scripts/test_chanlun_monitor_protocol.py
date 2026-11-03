"""Real Java/PostgreSQL restart/fault protocol checks on an isolated Docker net.

Own throwaway database and fixture ONLY; synthetic clocks are not live data.
"""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import subprocess
import time
import uuid


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path);args=p.parse_args()
    token=uuid.uuid4().hex[:10];network=f'aiquant-monitor-verify-{token}';db=f'{network}-db';peer=f'{network}-peer';java=f'{network}-java'
    created=[];checks=[];report=None
    root=Path(__file__).resolve().parents[1]
    def docker(*parts):
        return subprocess.run(['docker',*parts],check=True,capture_output=True,text=True,encoding='utf-8').stdout.strip()
    bridge="""import json,sys,urllib.request,urllib.error
url,body,expected=sys.argv[1:]; req=urllib.request.Request(url,data=None if body=='null' else body.encode(),headers={'Content-Type':'application/json'})
try:
 r=urllib.request.urlopen(req,timeout=110); code=r.status; data=r.read()
except urllib.error.HTTPError as e: code=e.code; data=e.read()
assert code==int(expected),(code,data.decode()); print(data.decode())
"""
    def call(path='',body=None,status=200,fixture=False):
        host='peer:8000' if fixture else 'java:8084/api/chanlun/v1/monitors'
        raw=docker('exec',peer,'python','-c',bridge,'http://'+host+path,json.dumps(body),str(status))
        return json.loads(raw) if raw else None
    def ready():
        for _ in range(60):
            if docker('inspect','--format','{{.State.Running}}',peer)!='true':
                raise RuntimeError('Isolated fixture exited before readiness')
            try:
                call();return
            except subprocess.CalledProcessError:time.sleep(1)
        raise RuntimeError('Isolated Java did not become ready')
    def create(suffix):
        body={'clientRequestId':str(uuid.uuid4()),'title':'TEST-MONITOR-'+suffix,'symbol':'FU2701','frequency':'MIN5'}
        r=call(body=body);assert call(body=body)['id']==r['id'];call(body={**body,'title':'changed'},status=409)
        for _ in range(15):
            r=call('/'+r['id']+'/check',{})
            if r['observedBars']:break
            time.sleep(1)
        assert r['observedBars']==221,r
        return r
    try:
        docker('network','create','--internal',network)
        docker('run','-d','--name',db,'--network',network,'--network-alias','db','-e','POSTGRES_DB=aiquant','-e','POSTGRES_USER=aiquant','-e','POSTGRES_PASSWORD=isolated-fixture-only','postgres:17.6-alpine3.22');created.append(db)
        docker('run','-d','--name',peer,'--network',network,'--network-alias','peer','--read-only','--tmpfs','/tmp',
               '-e','PYTHONPATH=/verification','-v',str(root)+':/verification:ro','-w','/verification','--entrypoint','python','ai-quant-algorithm-service','tests/integration/chanlun_monitor_peer.py');created.append(peer)
        for _ in range(40):
            try:docker('exec',db,'pg_isready','-h','127.0.0.1','-U','aiquant','-d','aiquant');break
            except subprocess.CalledProcessError:time.sleep(1)
        docker('run','-d','--name',java,'--network',network,'--network-alias','java','-e','DATABASE_URL=jdbc:postgresql://db:5432/aiquant','-e','DATABASE_USERNAME=aiquant','-e','DATABASE_PASSWORD=isolated-fixture-only','-e','CHANLUN_ALGORITHM_URL=http://peer:8000','ai-quant-chanlun-service');created.append(java)
        ready();r=create('main');identifier=r['id'];assert r['events'] and all(e['inboxState']=='SUPPRESSED_BOOTSTRAP' for e in r['events']);checks.append('bootstrap_suppressed_idempotent_create_conflict')
        original=r['events'];profile=r['profileHash']
        # Model a publish arriving between the head read and the event read.
        # The response must honor its captured head watermark, even if a newer
        # event row is already visible. The injected row belongs to this DB only.
        future_seq=r['analysis']['lastEventSeq']+100
        injection={**original[0]['payload'],'eventSeq':future_seq,'observedIndex':300}
        literal=json.dumps(injection).replace("'","''")
        docker('exec',db,'psql','-U','aiquant','-d','aiquant','-v','ON_ERROR_STOP=1','-c',f"insert into chanlun.monitor_event(monitor_id,event_seq,structure_id,snapshot_id,payload,inbox_state) select id,{future_seq},'{injection['id']}',latest_snapshot_id,'{literal}'::jsonb,'SUPPRESSED_BACKFILL' from chanlun.monitor where id='{identifier}'")
        assert call('/'+identifier)['events']==original
        docker('exec',db,'psql','-U','aiquant','-d','aiquant','-v','ON_ERROR_STOP=1','-c',f"delete from chanlun.monitor_event where monitor_id='{identifier}' and event_seq={future_seq}")
        checks.append('response_events_bound_to_captured_head_watermark')
        call('/fixture',{'status':'DISCONNECTED'},fixture=True);r=call('/'+identifier+'/check',{})
        assert r['status']=='DISCONNECTED' and r['observedBars']==221 and r['events']==original;checks.append('disconnect_keeps_watermark_and_events')
        call('/fixture',{'status':'READY','prefix':276},fixture=True);r=call('/'+identifier+'/check',{})
        assert r['observedBars']==276 and r['profileHash']==profile
        fresh=[e for e in r['events'] if e['inboxState']=='NEW'];assert fresh,r
        seq=fresh[0]['eventSeq'];seen=r['events'];r=call('/'+identifier+'/check',{})
        assert r['events']==seen;checks.append('recovery_catches_up_without_duplicate_events')
        frozen=call(f'/{identifier}/events/{seq}');assert frozen['analysis']['observedBars']==frozen['event']['observedIndex']+1
        assert len(frozen['analysis']['structures'])==1
        note={'clientRequestId':str(uuid.uuid4()),'outlook':'WAIT','content':'ISOLATED_PROTOCOL_REVIEW','lessonNumber':21}
        saved=call(f'/{identifier}/events/{seq}/reviews',note);assert call(f'/{identifier}/events/{seq}/reviews',note)['id']==saved['id']
        call(f'/{identifier}/events/{seq}/reviews',{**note,'content':'changed'},status=409);checks.append('immutable_prefix_review_idempotence_conflict')
        def snapshot_count():
            return int(docker('exec',db,'psql','-U','aiquant','-d','aiquant','-At','-c',f"select count(*) from chanlun.monitor_snapshot where monitor_id='{identifier}'"))
        snapshots=snapshot_count()
        assert snapshots==2,snapshots
        frozen_before=call(f'/{identifier}/events/{seq}')
        for prefix in (277,278):
            call('/fixture',{'prefix':prefix},fixture=True);r=call('/'+identifier+'/check',{})
            assert r['observedBars']==prefix and r['analysis']['observedBars']==prefix,r
            assert snapshot_count()==snapshots
        assert call(f'/{identifier}/events/{seq}')==frozen_before
        checks.append('non_signal_append_updates_current_head_without_snapshot_growth_or_review_change')
        call(f'/{identifier}/events/{seq}/ack',{});r=call('/'+identifier);assert next(e for e in r['events'] if e['eventSeq']==seq)['inboxState']=='ACKNOWLEDGED'
        call('/'+identifier+'/control',{'enabled':False});call('/fixture',{'prefix':287},fixture=True);assert call('/'+identifier+'/check',{})['observedBars']==278
        call('/'+identifier+'/control',{'enabled':True});r=call('/'+identifier+'/check',{});assert r['observedBars']==287;checks.append('pause_and_resume_preserve_watermark')
        docker('stop',java)
        # Simulate an expired lease left by an interrupted owner, in OWN database.
        docker('exec',db,'psql','-U','aiquant','-d','aiquant','-v','ON_ERROR_STOP=1','-c',f"update chanlun.monitor set lease_id='{uuid.uuid4()}',lease_until=now()-interval '1 second',next_check_at=now() where id='{identifier}'")
        docker('start',java);ready();r=call('/'+identifier+'/check',{});assert r['observedBars']==287 and r['profileHash']==profile
        assert any(n['id']==saved['id'] for n in call('/reviews'));checks.append('restart_expired_lease_recovers_persisted_events_and_review')
        call('/fixture',{'revision':True},fixture=True);r=call('/'+identifier+'/check',{});assert r['status']=='INPUT_REVISED' and not r['enabled'] and r['observedBars']==287;checks.append('revised_sealed_input_pauses_without_overwrite')
        call('/fixture',{'prefix':221,'revision':False},fixture=True);other=create('version')
        call('/fixture',{'version':True,'prefix':276},fixture=True);v=call('/'+other['id']+'/check',{});assert v['status']=='VERSION_CHANGED' and not v['enabled'] and v['observedBars']==221;checks.append('profile_drift_pauses_without_mixing_versions')
        report={'status':'PASS','verifiedAt':datetime.now(timezone.utc).isoformat(),'scope':'ISOLATED_JAVA_POSTGRES_SYNTHETIC_CLOCKS_NOT_LIVE_MARKET','checks':checks,'cleanupCompleted':False}
    except Exception:
        for name in (java,peer):
            if name in created:
                result=subprocess.run(['docker','logs','--tail','45',name],capture_output=True,text=True,encoding='utf-8')
                print(result.stdout);print(result.stderr)
        raise
    finally:
        for name in reversed(created):docker('rm','-f',name)
        docker('network','rm',network)
        if report:report['cleanupCompleted']=True
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
