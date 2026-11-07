"""Read-only release verification: private baseline IDs stay local; no production fixtures/users created."""
import argparse,base64,hashlib,hmac,json,re,subprocess,time,uuid,urllib.error
from datetime import datetime,timezone
from pathlib import Path
from verify_decision_deployment import command,sql,http
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/implementation/private-plan-alerts-2026-11-07'
BASE=ROOT/'.test-tmp/private-alert-production-before-private.json'
SERVICES=['identity-service','paper-trading-service','frontend']
TABLES={**{'paper_trading.'+t:'id' for t in ['paper_session','paper_order','paper_fill','strategy_workflow_version','decision_case','decision_plan','decision_review','decision_research_source']},'paper_trading.decision_paper':'plan_id','paper_trading.decision_source_link':'source_id',**{'market.'+t:'id' for t in ['live_monitor','live_monitor_event','live_monitor_history']}}
TABLES['paper_trading.decision_monitor']="(plan_id::text||':'||monitor_id::text)"
TABLES.update({'identity.'+t:'id' for t in ['account','tenant','session','api_key','access_role','menu']})
TABLES['identity.membership']="(tenant_id::text||':'||user_id::text)"
TABLES['identity.role_assignment']="(tenant_id::text||':'||user_id::text||':'||role_id::text)"
def identifiers():
    return {t:sql("select coalesce(json_agg("+k+"::text order by "+k+"),'[]'::json) from "+t) for t,k in TABLES.items()}
def images():return {s:command('docker','inspect','--format','{{.Image}}','ai-quant-'+s+'-1') for s in SERVICES}
def probe(secret,permissions,path):
    payload=base64.urlsafe_b64encode(json.dumps({'userId':str(uuid.uuid4()),'tenantId':str(uuid.uuid4()),'role':'VIEWER','permissions':permissions,'expiresAt':int(time.time())+30},separators=(',',':')).encode()).decode().rstrip('=')
    token=payload+'.'+base64.urlsafe_b64encode(hmac.new(secret.encode(),payload.encode(),hashlib.sha256).digest()).decode().rstrip('=')
    result=subprocess.run(['docker','exec','ai-quant-paper-trading-service-1','curl','-sS','--max-time','10','-w','\n%{http_code}','-H','X-Aiquant-Identity: '+token,'http://localhost:8083'+path],capture_output=True,text=True,encoding='utf-8',timeout=15)
    if result.returncode:raise RuntimeError('Internal read-only request failed')
    body,status=result.stdout.rsplit('\n',1);return int(status),json.loads(body)
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--snapshot',action='store_true');args=parser.parse_args();OUT.mkdir(parents=True,exist_ok=True)
    if args.snapshot:
        ids=identifiers();BASE.write_text(json.dumps(ids),encoding='utf-8')
        (OUT/'pre-deploy.json').write_text(json.dumps({'scope':'READ_ONLY_BASELINE_NO_BUSINESS_CONTENT','recordedAtUtc':datetime.now(timezone.utc).isoformat(),'counts':{t:len(v) for t,v in ids.items()},'images':images()},indent=2)+'\n',encoding='utf-8');print('Read-only baseline saved; original identifiers retained only in local ignored test directory.');return
    before=json.loads(BASE.read_text(encoding='utf-8'));assert set(before)==set(TABLES)
    health={}
    for _ in range(45):
        health={s:command('docker','inspect','--format','{{.State.Health.Status}}','ai-quant-'+s+'-1') for s in SERVICES}
        if all(v=='healthy' for v in health.values()):break
        time.sleep(1)
    assert all(v=='healthy' for v in health.values()),health
    after=identifiers();tables={}
    for t in TABLES:
        assert set(before[t])<=set(after[t]),'Original identifiers missing in '+t
        tables[t]={'before':len(before[t]),'after':len(after[t]),'allOriginalIdsPreserved':True,'afterIdsSha256':hashlib.sha256(json.dumps(sorted(after[t])).encode()).hexdigest()}
    migration=sql("select to_json(version) from paper_trading.flyway_schema_history where success order by installed_rank desc limit 1");assert migration=='13'
    entry=http(re.search(r'src="([^"]*/assets/index-[^"]+\.js)"',http('/today'))[1]);chunk=re.search(r'DecisionDeskView-[A-Za-z0-9_-]+\.js',entry)[0];assert '本计划专属提醒' in http('/assets/'+chunk)
    try:http('/api/v1/paper/decisions/alerts/events');raise AssertionError('Anonymous private inbox accepted')
    except urllib.error.HTTPError as error:assert error.code==401
    values={}
    for line in (ROOT/'infrastructure/.env').read_text(encoding='utf-8-sig').splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            k,v=line.split('=',1);values[k.strip()]=v.strip().strip(chr(34)).strip(chr(39))
    checks=[]
    for suffix,expected in [('/alerts/events',200),('/alerts/events?unread=true&page=2',200),('/inbox?filter=UNKNOWN',400)]:
        status,body=probe(values['IDENTITY_INTERNAL_SECRET'],['market.read','paper.read'],'/api/v1/paper/decisions'+suffix);assert status==expected
        if status==200:assert body['items']==[] and body['total']==0
        checks.append({'suffix':suffix,'status':status,'randomEmptyWorkspace':True})
    status,_=probe(values['IDENTITY_INTERNAL_SECRET'],['paper.read'],'/api/v1/paper/decisions/alerts/events');assert status==403
    flags=sql("select json_build_object('rls',relrowsecurity,'forceRls',relforcerowsecurity) from pg_class where oid='paper_trading.decision_monitor'::regclass");assert flags['rls'] and flags['forceRls']
    flags['updateAllowed']=sql("select to_json(has_table_privilege('aiquant_tenant','paper_trading.decision_monitor','UPDATE'))")
    flags['deleteAllowed']=sql("select to_json(has_table_privilege('aiquant_tenant','paper_trading.decision_monitor','DELETE'))")
    assert not flags['updateAllowed'] and not flags['deleteAllowed']
    alertFlags=sql("select json_agg(json_build_object('table',relname,'rls',relrowsecurity,'forceRls',relforcerowsecurity)) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='paper_trading' and relname in ('decision_alert_subscription','decision_alert_event')");assert len(alertFlags)==2 and all(f['rls'] and f['forceRls'] for f in alertFlags)
    immutable=sql("select json_build_object('eventEvidenceUpdate',has_column_privilege('aiquant_tenant','paper_trading.decision_alert_event','evidence','UPDATE'),'eventDelete',has_table_privilege('aiquant_tenant','paper_trading.decision_alert_event','DELETE'),'ownerUpdate',has_column_privilege('aiquant_tenant','paper_trading.decision_alert_subscription','owner_id','UPDATE'),'ackAllowed',has_column_privilege('aiquant_tenant','paper_trading.decision_alert_event','acknowledged_at','UPDATE'))");assert not immutable['eventEvidenceUpdate'] and not immutable['eventDelete'] and not immutable['ownerUpdate'] and immutable['ackAllowed']
    counts=sql("select json_build_object('subscriptions',(select count(*) from paper_trading.decision_alert_subscription),'enabledSubscriptions',(select count(*) from paper_trading.decision_alert_subscription where enabled),'events',(select count(*) from paper_trading.decision_alert_event),'sharedEnabledJobs',(select count(*) from market.live_monitor where enabled))")
    result=subprocess.run(['docker','exec','ai-quant-identity-service-1','curl','-sS','--max-time','10','-H','X-Identity-Service-Secret: '+values['IDENTITY_INTERNAL_SECRET'],'-H','Content-Type: application/json','-d',json.dumps({'userId':str(uuid.uuid4()),'tenantId':str(uuid.uuid4())}),'http://localhost:8085/internal/v1/identity/decision-authorization'],capture_output=True,text=True,encoding='utf-8',timeout=15)
    assert result.returncode==0 and json.loads(result.stdout)['allowed'] is False
    identityUrl=command('docker','exec','ai-quant-paper-trading-service-1','printenv','IDENTITY_SERVICE_URL');assert identityUrl=='http://identity-service:8085'
    schedulerEnabled=command('docker','exec','ai-quant-paper-trading-service-1','printenv','PLAN_ALERT_SCHEDULER_ENABLED');assert schedulerEnabled=='true'
    threads=command('docker','exec','ai-quant-paper-trading-service-1','sh','-c','cat /proc/[0-9]*/task/*/comm 2>/dev/null || true');assert any(t.startswith('plan-alert-disp') for t in threads.splitlines())
    gatewayHealth=command('docker','inspect','--format','{{.State.Health.Status}}','ai-quant-gateway-service-1');assert gatewayHealth=='healthy'
    gatewayImage=command('docker','inspect','--format','{{.Image}}','ai-quant-gateway-service-1');assert gatewayImage==json.loads((OUT/'pre-deploy.json').read_text(encoding='utf-8'))['gatewayImageBeforeConnectionRefresh']
    receipt={'schedulerEnabled':schedulerEnabled,'dispatcherObserved':True,'gatewayConnectionRefresh':{'health':gatewayHealth,'imageUnchanged':True},'alertRls':alertFlags,'immutableEventGrants':immutable,'currentCounts':counts,'unknownIdentityAllowed':False,'identityServiceUrl':identityUrl,'monitorLinkRls':flags,'scope':'READ_ONLY_RELEASE_VERIFICATION_NO_PRODUCTION_USERS_OR_RECORDS_CREATED','verifiedAtUtc':datetime.now(timezone.utc).isoformat(),'result':'PASSED','health':health,'tables':tables,'migration':migration,'anonymousAlertFeedStatus':401,'missingMarketPermissionStatus':status,'internalRandomIdentityChecks':checks,'frontendBundle':chunk,'images':images()}
    (OUT/'deployment.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps({'result':'PASSED','health':health,'migration':migration,'allOriginalIdsPreserved':True,'privateAlertChecks':len(checks)+2}))
if __name__=='__main__':main()
