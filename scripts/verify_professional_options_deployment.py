"""Read-only frontend rollout checks; no production fixtures, account creation or business writes."""
import argparse,hashlib,json,re,time,urllib.error
from datetime import datetime,timezone
from pathlib import Path
from verify_private_alert_deployment import TABLES,identifiers,images,command,sql,http
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'docs/implementation/professional-options-2026-11-08';BASE=ROOT/'.test-tmp/professional-options-production-before-private.json'
TABLES['paper_trading.decision_alert_subscription']='plan_id'
TABLES['paper_trading.decision_alert_event']='id'
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--snapshot',action='store_true');args=parser.parse_args();OUT.mkdir(parents=True,exist_ok=True)
    if args.snapshot:
        ids=identifiers();BASE.write_text(json.dumps(ids),encoding='utf-8')
        (OUT/'pre-deploy.json').write_text(json.dumps({'scope':'READ_ONLY_BASELINE_NO_BUSINESS_CONTENT','recordedAtUtc':datetime.now(timezone.utc).isoformat(),'counts':{t:len(v) for t,v in ids.items()},'images':images()},indent=2)+'\n',encoding='utf-8');print('Read-only baseline saved; raw IDs remain in the ignored local directory.');return
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
    pre=json.loads((OUT/'pre-deploy.json').read_text(encoding='utf-8'));current=images()
    for service in ['identity-service','paper-trading-service']:assert current[service]==pre['images'][service]
    migration=sql("select to_json(version) from paper_trading.flyway_schema_history where success order by installed_rank desc limit 1");assert migration=='14'
    entryPath=re.search(r'src="([^"]*/assets/index-[^"]+\.js)"',http('/options'))[1];entry=http(entryPath)
    localEntry=re.search(r'src="([^"]*/assets/index-[^"]+\.js)"',(ROOT/'frontend/dist/index.html').read_text(encoding='utf-8'))[1]
    assert entryPath==localEntry
    assert hashlib.sha256(entry.encode()).hexdigest()==hashlib.sha256((ROOT/'frontend/dist'/entryPath.lstrip('/')).read_bytes()).hexdigest()
    chunk=re.search(r'OptionsView-[A-Za-z0-9_-]+\.js',entry)[0];assert '期货计划仅作参考关联' in http('/assets/'+chunk)
    statuses={}
    for path in ['/api/v1/options/catalog','/api/v1/paper/decisions/']:
        try:http(path);raise AssertionError('Anonymous business API accepted')
        except urllib.error.HTTPError as error:assert error.code==401;statuses[path]=error.code
    receipt={'scope':'FRONTEND_ONLY_READ_ONLY_DEPLOYMENT_NO_PRODUCTION_FIXTURES_OR_WRITES','result':'PASSED','verifiedAtUtc':datetime.now(timezone.utc).isoformat(),'health':health,'migration':migration,'backendImagesUnchanged':True,'tables':tables,'images':current,'frontendEntry':entryPath,'entryMatchesValidatedBuild':True,'optionsBundle':chunk,'anonymousBusinessStatuses':statuses}
    (OUT/'deployment.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps({'result':'PASSED','health':health,'migration':migration,'backendImagesUnchanged':True,'allOriginalIdsPreserved':True}))
if __name__=='__main__':main()
