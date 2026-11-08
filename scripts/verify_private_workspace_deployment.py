"""Read-only rollout verification; no production users, sessions or preference fixtures."""
import argparse,hashlib,json,re,time,urllib.error
from datetime import datetime,timezone
from pathlib import Path
from verify_chanlun_context_deployment import TABLES,identifiers,images,frozen,command,sql,http
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/implementation/private-workspace-2026-11-08'
BASE=ROOT/'.test-tmp/private-workspace-production-before-private.json'
def versions():return {s:sql('select to_json(version) from '+s+'.flyway_schema_history where success order by installed_rank desc limit 1') for s in ['identity','paper_trading','chanlun']}
def main():
    p=argparse.ArgumentParser();p.add_argument('--snapshot',action='store_true');args=p.parse_args();OUT.mkdir(parents=True,exist_ok=True)
    if args.snapshot:
        ids=identifiers();evidence=frozen();BASE.write_text(json.dumps({'ids':ids,'frozen':evidence}),encoding='utf-8')
        receipt={'scope':'READ_ONLY_BASELINE_NO_BUSINESS_CONTENT','recordedAtUtc':datetime.now(timezone.utc).isoformat(),'counts':{t:len(v) for t,v in ids.items()},'frozenCounts':{t:len(v) for t,v in evidence.items()},'migrations':versions(),'images':images(),'gatewayImage':command('docker','inspect','--format','{{.Image}}','ai-quant-gateway-service-1')}
        (OUT/'pre-deploy.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8');print('Read-only baseline saved; original IDs remain only in ignored local files.');return
    before=json.loads(BASE.read_text(encoding='utf-8'));pre=json.loads((OUT/'pre-deploy.json').read_text(encoding='utf-8'))
    for _ in range(45):
        health={s:command('docker','inspect','--format','{{.State.Health.Status}}','ai-quant-'+s+'-1') for s in ['frontend','identity-service','paper-trading-service','chanlun-service','gateway-service']}
        if all(v=='healthy' for v in health.values()):break
        time.sleep(1)
    assert all(v=='healthy' for v in health.values()),health
    after=identifiers();tables={}
    for t in TABLES:
        assert set(before['ids'][t])<=set(after[t]),'Original IDs missing: '+t
        tables[t]={'before':len(before['ids'][t]),'after':len(after[t]),'allOriginalIdsPreserved':True,'afterIdsSha256':hashlib.sha256(json.dumps(sorted(after[t])).encode()).hexdigest()}
    frozen_after=frozen();frozen_checks={}
    for table,values in before['frozen'].items():
        assert all(frozen_after[table].get(k)==v for k,v in values.items()),'Frozen evidence changed: '+table
        frozen_checks[table]={'originalRecordsChecked':len(values),'originalResultsUnchanged':True}
    current=images()
    for s in ['paper-trading-service','chanlun-service']:assert current[s]==pre['images'][s]
    gateway=command('docker','inspect','--format','{{.Image}}','ai-quant-gateway-service-1');assert gateway==pre['gatewayImage']
    migration=versions();assert migration=={'identity':'4','paper_trading':'14','chanlun':'8'},migration
    flags=sql("select json_agg(json_build_object('table',relname,'rls',relrowsecurity,'forceRls',relforcerowsecurity)) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='identity' and relname in ('workspace_document','workspace_revision')")
    assert len(flags)==2 and all(f['rls'] and f['forceRls'] for f in flags)
    grants=sql("select json_build_object('accountRead',has_table_privilege('aiquant_workspace','identity.account','SELECT'),'ownerUpdate',has_column_privilege('aiquant_workspace','identity.workspace_document','owner_id','UPDATE'),'revisionUpdate',has_table_privilege('aiquant_workspace','identity.workspace_revision','UPDATE'),'revisionDelete',has_table_privilege('aiquant_workspace','identity.workspace_revision','DELETE'),'contentUpdate',has_column_privilege('aiquant_workspace','identity.workspace_document','content','UPDATE'))")
    assert grants=={'accountRead':False,'ownerUpdate':False,'revisionUpdate':False,'revisionDelete':False,'contentUpdate':True}
    role=sql("select json_build_object('login',rolcanlogin,'superuser',rolsuper,'bypassRls',rolbypassrls) from pg_roles where rolname='aiquant_workspace'");assert not any(role.values())
    statuses={}
    for endpoint in ['/api/v1/auth/workspace/preferences','/api/v1/auth/workspace/charts/RB2701/900','/api/v1/paper/decisions/']:
        try:http(endpoint);raise AssertionError('Anonymous private API accepted')
        except urllib.error.HTTPError as e:assert e.code==401;statuses[endpoint]=e.code
    entry_path=re.search(r'src="([^\"]*/assets/index-[^\"]+\.js)"',http('/live'))[1]
    local_path=re.search(r'src="([^\"]*/assets/index-[^\"]+\.js)"',(ROOT/'frontend/dist/index.html').read_text(encoding='utf-8'))[1];assert entry_path==local_path
    entry=http(entry_path);assert hashlib.sha256(entry.encode()).hexdigest()==hashlib.sha256((ROOT/'frontend/dist'/entry_path.lstrip('/')).read_bytes()).hexdigest()
    assert '/api/v1/auth/workspace/preferences' in entry
    counts=sql("select json_build_object('documents',(select count(*) from identity.workspace_document),'revisions',(select count(*) from identity.workspace_revision))")
    receipt={'scope':'READ_ONLY_RELEASE_VERIFICATION_NO_PRODUCTION_FIXTURES_OR_WRITES','result':'PASSED','verifiedAtUtc':datetime.now(timezone.utc).isoformat(),'health':health,'migrations':migration,'rls':flags,'restrictedGrants':grants,'role':role,'tables':tables,'frozenEvidence':frozen_checks,'images':current,'paperAndChanlunImagesUnchanged':True,'gatewayImageUnchanged':True,'frontendEntry':entry_path,'entryMatchesValidatedBuild':True,'anonymousPrivateStatuses':statuses,'privateRecordCounts':counts}
    (OUT/'deployment.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps({'result':'PASSED','health':health,'migrations':migration,'allOriginalIdsPreserved':True,'originalFrozenResultsUnchanged':True,'privateRecordCounts':counts}))
if __name__=='__main__':main()
