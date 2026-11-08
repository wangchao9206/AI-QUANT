"""Read-only frontend rollout checks, including original Chanlun IDs and frozen result fingerprints."""
import argparse,hashlib,json,re,time,urllib.error
from datetime import datetime,timezone
from pathlib import Path
from verify_private_alert_deployment import TABLES,identifiers,images as base_images,command,sql,http
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'docs/implementation/chanlun-context-2026-11-08';BASE=ROOT/'.test-tmp/chanlun-context-production-before-private.json'
TABLES['paper_trading.decision_alert_subscription']='plan_id';TABLES['paper_trading.decision_alert_event']='id'
for name in ['analysis_run','judgment','replay_session','replay_decision','replay_advance','lab_experiment','monitor','monitor_snapshot','monitor_review','multiframe_run','comparison']:TABLES['chanlun.'+name]='id'
TABLES['chanlun.structure_event']="(run_id::text||':'||event_seq::text)"
TABLES['chanlun.monitor_event']="(monitor_id::text||':'||event_seq::text)"
TABLES['chanlun.comparison_member']="(comparison_id::text||':'||run_id::text)"
def images():return {**base_images(),'chanlun-service':command('docker','inspect','--format','{{.Image}}','ai-quant-chanlun-service-1')}
def frozen():return {table:sql("select coalesce(json_object_agg(id::text,md5(result::text)),'{}'::json) from chanlun."+table+" where status='SUCCEEDED' and result is not null") for table in ['analysis_run','multiframe_run','comparison']}
def migrations():return {schema:sql("select to_json(version) from "+schema+".flyway_schema_history where success order by installed_rank desc limit 1") for schema in ['paper_trading','chanlun']}
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--snapshot',action='store_true');args=parser.parse_args();OUT.mkdir(parents=True,exist_ok=True)
    if args.snapshot:
        ids=identifiers();fingerprints=frozen();BASE.write_text(json.dumps({'ids':ids,'frozen':fingerprints}),encoding='utf-8')
        (OUT/'pre-deploy.json').write_text(json.dumps({'scope':'READ_ONLY_BASELINE_NO_BUSINESS_CONTENT','recordedAtUtc':datetime.now(timezone.utc).isoformat(),'counts':{t:len(v) for t,v in ids.items()},'frozenCounts':{t:len(v) for t,v in fingerprints.items()},'migrations':migrations(),'images':images()},indent=2)+'\n',encoding='utf-8');print('Read-only baseline saved; raw IDs and fingerprints remain in ignored local directory.');return
    baseline=json.loads(BASE.read_text(encoding='utf-8'));before=baseline['ids'];assert set(before)==set(TABLES)
    for _ in range(45):
        health={s:command('docker','inspect','--format','{{.State.Health.Status}}','ai-quant-'+s+'-1') for s in ['frontend','paper-trading-service','identity-service','chanlun-service','gateway-service']}
        if all(v=='healthy' for v in health.values()):break
        time.sleep(1)
    assert all(v=='healthy' for v in health.values()),health
    after=identifiers();tables={}
    for t in TABLES:
        assert set(before[t])<=set(after[t]),'Missing original IDs in '+t
        tables[t]={'before':len(before[t]),'after':len(after[t]),'allOriginalIdsPreserved':True,'afterIdsSha256':hashlib.sha256(json.dumps(sorted(after[t])).encode()).hexdigest()}
    frozen_after=frozen();frozen_checks={}
    for table,values in baseline['frozen'].items():
        assert all(frozen_after[table].get(k)==v for k,v in values.items()),'Existing frozen evidence changed: '+table
        frozen_checks[table]={'originalRecordsChecked':len(values),'originalResultsUnchanged':True}
    pre=json.loads((OUT/'pre-deploy.json').read_text(encoding='utf-8'));current=images()
    for service in ['identity-service','paper-trading-service','chanlun-service']:assert current[service]==pre['images'][service]
    versions=migrations();assert versions==pre['migrations']
    entryPath=re.search(r'src="([^"]*/assets/index-[^"]+\.js)"',http('/chanlun/multiframe'))[1];entry=http(entryPath)
    localEntry=re.search(r'src="([^"]*/assets/index-[^"]+\.js)"',(ROOT/'frontend/dist/index.html').read_text(encoding='utf-8'))[1];assert entryPath==localEntry
    assert hashlib.sha256(entry.encode()).hexdigest()==hashlib.sha256((ROOT/'frontend/dist'/entryPath.lstrip('/')).read_bytes()).hexdigest()
    chunk=re.search(r'MultiframeView-[A-Za-z0-9_-]+\.js',entry)[0];assert '查看当前行情并保留观察回链' in http('/assets/'+chunk)
    statuses={}
    for path in ['/api/chanlun/v1/multiframe','/api/chanlun/v1/datasets','/api/v1/paper/decisions/']:
        try:http(path);raise AssertionError('Anonymous business API accepted')
        except urllib.error.HTTPError as error:assert error.code==401;statuses[path]=error.code
    receipt={'scope':'FRONTEND_ONLY_READ_ONLY_DEPLOYMENT_NO_PRODUCTION_FIXTURES_OR_WRITES','result':'PASSED','verifiedAtUtc':datetime.now(timezone.utc).isoformat(),'health':health,'migrations':versions,'backendImagesUnchanged':True,'tables':tables,'frozenEvidence':frozen_checks,'images':current,'frontendEntry':entryPath,'entryMatchesValidatedBuild':True,'multiframeBundle':chunk,'anonymousBusinessStatuses':statuses}
    (OUT/'deployment.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps({'result':'PASSED','health':health,'migrations':versions,'backendImagesUnchanged':True,'allOriginalIdsPreserved':True,'originalFrozenResultsUnchanged':True}))
if __name__=='__main__':main()
