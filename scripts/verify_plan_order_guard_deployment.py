"""Read-only V14 rollout verification. Identifiers and credentials never enter published receipts."""
import argparse,hashlib,json,re,time,urllib.error
from datetime import datetime,timezone
from pathlib import Path
from verify_private_alert_deployment import TABLES,identifiers,images,command,sql,http,probe
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'docs/implementation/plan-order-guards-2026-11-07';BASE=ROOT/'.test-tmp/plan-guard-production-before-private.json'
TABLES['paper_trading.decision_alert_subscription']='plan_id'
TABLES['paper_trading.decision_alert_event']='id'
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--snapshot',action='store_true');args=parser.parse_args();OUT.mkdir(parents=True,exist_ok=True)
    if args.snapshot:
        ids=identifiers();BASE.write_text(json.dumps(ids),encoding='utf-8')
        (OUT/'pre-deploy.json').write_text(json.dumps({'scope':'READ_ONLY_BASELINE_NO_BUSINESS_CONTENT','recordedAtUtc':datetime.now(timezone.utc).isoformat(),'counts':{t:len(v) for t,v in ids.items()},'images':images()},indent=2)+'\n',encoding='utf-8');print('Read-only baseline saved; raw IDs retained in ignored local directory.');return
    before=json.loads(BASE.read_text(encoding='utf-8'));assert set(before)==set(TABLES)
    for _ in range(45):
        health={s:command('docker','inspect','--format','{{.State.Health.Status}}','ai-quant-'+s+'-1') for s in ['frontend','paper-trading-service','identity-service','gateway-service']}
        if all(v=='healthy' for v in health.values()):break
        time.sleep(1)
    assert all(v=='healthy' for v in health.values()),health
    after=identifiers();tables={}
    for t in TABLES:
        assert set(before[t])<=set(after[t]),'Missing original IDs in '+t
        tables[t]={'before':len(before[t]),'after':len(after[t]),'allOriginalIdsPreserved':True,'afterIdsSha256':hashlib.sha256(json.dumps(sorted(after[t])).encode()).hexdigest()}
    pre=json.loads((OUT/'pre-deploy.json').read_text(encoding='utf-8'));current=images();assert current['identity-service']==pre['images']['identity-service']
    migration=sql("select to_json(version) from paper_trading.flyway_schema_history where success order by installed_rank desc limit 1");assert migration=='14'
    guards=sql("select json_build_object('guardedSessions',(select count(*) from paper_trading.paper_session where decision_guarded),'unguardedLinkedSessions',(select count(*) from paper_trading.decision_paper d join paper_trading.paper_session s on s.id=d.session_id and s.tenant_id=d.tenant_id where not s.decision_guarded))");assert guards['unguardedLinkedSessions']==0
    policies=sql("select json_agg(json_build_object('table',relname,'rls',relrowsecurity,'forceRls',relforcerowsecurity)) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='paper_trading' and relname in ('decision_case','decision_plan','decision_paper')");assert len(policies)==3 and all(p['rls'] and p['forceRls'] for p in policies)
    entryPath=re.search(r'src="([^"]*/assets/index-[^"]+\.js)"',http('/paper'))[1];entry=http(entryPath);chunk=re.search(r'PaperTradingView-[A-Za-z0-9_-]+\.js',entry)[0];assert '计划开仓约束' in http('/assets/'+chunk)
    localEntry=re.search(r'src="([^"]*/assets/index-[^"]+\.js)"',(ROOT/'frontend/dist/index.html').read_text(encoding='utf-8'))[1]
    assert entryPath==localEntry,'Deployed entry differs from the validated production build'
    assert hashlib.sha256(entry.encode()).hexdigest()==hashlib.sha256((ROOT/'frontend/dist'/entryPath.lstrip('/')).read_bytes()).hexdigest()
    try:http('/api/v1/paper/sessions');raise AssertionError('Anonymous ledger accepted')
    except urllib.error.HTTPError as error:assert error.code==401
    values={}
    for line in (ROOT/'infrastructure/.env').read_text(encoding='utf-8-sig').splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            k,v=line.split('=',1);values[k.strip()]=v.strip().strip(chr(34)).strip(chr(39))
    status,body=probe(values['IDENTITY_INTERNAL_SECRET'],['paper.read'],'/api/v1/paper/sessions');assert status==200 and body==[]
    missing,_=probe(values['IDENTITY_INTERNAL_SECRET'],[],'/api/v1/paper/sessions');assert missing==403
    receipt={'scope':'READ_ONLY_RELEASE_CHECK_NO_PRODUCTION_USERS_RECORDS_OR_ORDERS_CREATED','result':'PASSED','verifiedAtUtc':datetime.now(timezone.utc).isoformat(),'health':health,'migration':migration,'identityImageUnchanged':True,'tables':tables,'guards':guards,'privateRls':policies,'anonymousLedgerStatus':401,'emptyRandomTenantReadStatus':status,'missingPaperPermissionStatus':missing,'images':current,'frontendEntry':entryPath,'entryMatchesValidatedBuild':True,'paperBundle':chunk}
    (OUT/'deployment.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps({'result':'PASSED','health':health,'migration':migration,'allOriginalIdsPreserved':True,'unguardedLinkedSessions':0}))
if __name__=='__main__':main()
