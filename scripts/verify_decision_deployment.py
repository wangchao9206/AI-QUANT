"""Read-only deployment checks; never signs in, inserts fixtures or changes production records."""
import hashlib
import json
import re
import subprocess
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/implementation/decision-p0-2026-11-07'
BASE=ROOT/'.test-tmp/decision-production-before-private.json'
SERVICES=['identity-service','market-service','paper-trading-service','frontend']
def command(*args):
    return subprocess.check_output(args,text=True,encoding='utf-8').strip()
def sql(query):
    return json.loads(command('docker','exec','ai-quant-postgres-1','psql','-U','aiquant','-d','aiquant','-At','-c',query))
def http(path):
    with urllib.request.urlopen('http://127.0.0.1:8088'+path,timeout=10) as response:
        return response.read().decode('utf-8')
def main():
    before=json.loads(BASE.read_text(encoding='utf-8'))
    health={}
    for _ in range(45):
        health={s:command('docker','inspect','--format','{{.State.Health.Status}}','ai-quant-'+s+'-1') for s in SERVICES}
        if all(v=='healthy' for v in health.values()):break
        time.sleep(1)
    assert all(v=='healthy' for v in health.values()),health
    tables={}
    allowed={'paper_trading.paper_session','paper_trading.paper_order','paper_trading.paper_fill','paper_trading.strategy_workflow_version','market.live_monitor','market.live_monitor_event','market.live_monitor_history'}
    assert set(before)==allowed
    for table,ids in before.items():
        after=sql("select coalesce(json_agg(id::text order by id),'[]'::json) from "+table)
        missing=set(ids)-set(after);assert not missing,'Missing original identifiers in '+table
        tables[table]={'before':len(ids),'after':len(after),'allOriginalIdsPreserved':True,'afterIdsSha256':hashlib.sha256(json.dumps(sorted(after)).encode()).hexdigest()}
    policies=sql("select json_agg(json_build_object('table',relname,'rls',relrowsecurity,'forceRls',relforcerowsecurity)) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='paper_trading' and relname in ('decision_case','decision_plan','decision_review','decision_paper')")
    assert len(policies)==4 and all(r['rls'] and r['forceRls'] for r in policies)
    version=sql("select to_json(version) from paper_trading.flyway_schema_history where success order by installed_rank desc limit 1")
    assert version=='10',version
    counts=sql("select json_build_object('cases',(select count(*) from paper_trading.decision_case),'plans',(select count(*) from paper_trading.decision_plan),'reviews',(select count(*) from paper_trading.decision_review),'paperLinks',(select count(*) from paper_trading.decision_paper),'enabledMonitorJobs',(select count(*) from market.live_monitor where enabled))")
    index=http('/paper/decisions')
    main_js=re.search(r'src="([^"]*/assets/index-[^"]+\.js)"',index)
    assert main_js,'Frontend entry not found'
    entry=http(main_js[1]);chunk=re.search(r'DecisionDeskView-[A-Za-z0-9_-]+\.js',entry)
    assert chunk,'Decision route is absent from deployed frontend'
    assert '从原事件形成自己的计划' in http('/assets/'+chunk[0])
    try:http('/api/v1/paper/decisions');raise AssertionError('Unauthenticated API access accepted')
    except urllib.error.HTTPError as error:assert error.code==401,error.code
    receipt={'scope':'READ_ONLY_PRODUCTION_DEPLOYMENT_CHECK_NO_SYNTHETIC_RECORDS_INSERTED','verifiedAtUtc':datetime.now(timezone.utc).isoformat(),'result':'PASSED','health':health,'tables':tables,'migration':version,'policies':policies,'currentCounts':counts,'frontendBundle':chunk[0],'anonymousDecisionApi':401,'images':{s:command('docker','inspect','--format','{{.Image}}','ai-quant-'+s+'-1') for s in SERVICES},'mode':json.loads((ROOT/'infrastructure/.deployment-mode.json').read_text(encoding='utf-8'))['mode']}
    (OUT/'deployment.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'result':'PASSED','health':health,'migration':version,'allOriginalRecordsPreserved':True,'currentCounts':counts},ensure_ascii=False))
if __name__=='__main__':main()
