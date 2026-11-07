"""Read-only V11 rollout verification. Does not create users, research receipts or imports."""
import hashlib,json,re,time,urllib.error
from datetime import datetime,timezone
from pathlib import Path
from verify_decision_deployment import command,sql,http
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'docs/implementation/research-decisions-2026-11-07'
SERVICES=['paper-trading-service','frontend']
def main():
 before=json.loads((ROOT/'.test-tmp/research-decision-production-before-private.json').read_text(encoding='utf-8'))
 allowed={'paper_trading.paper_session','paper_trading.paper_order','paper_trading.paper_fill','paper_trading.strategy_workflow_version','market.live_monitor','market.live_monitor_event','market.live_monitor_history','paper_trading.decision_case','paper_trading.decision_plan','paper_trading.decision_review','paper_trading.decision_paper'}
 assert set(before)==allowed
 for _ in range(45):
  health={s:command('docker','inspect','--format','{{.State.Health.Status}}','ai-quant-'+s+'-1') for s in SERVICES}
  if all(v=='healthy' for v in health.values()):break
  time.sleep(1)
 assert all(v=='healthy' for v in health.values()),health
 tables={}
 for table,ids in before.items():
  key='plan_id' if table.endswith('.decision_paper') else 'id';after=sql("select coalesce(json_agg("+key+"::text order by "+key+"),'[]'::json) from "+table)
  assert set(ids)<=set(after),'Missing original identifiers in '+table
  tables[table]={'before':len(ids),'after':len(after),'allOriginalIdsPreserved':True,'afterIdsSha256':hashlib.sha256(json.dumps(sorted(after)).encode()).hexdigest()}
 version=sql("select to_json(version) from paper_trading.flyway_schema_history where success order by installed_rank desc limit 1");assert version=='11'
 policies=sql("select json_agg(json_build_object('table',tablename,'qual',qual,'check',with_check)) from pg_policies where schemaname='paper_trading' and tablename in ('decision_research_source','decision_source_link')")
 assert len(policies)==2 and all('app.user_id' in p['qual'] and 'app.research_read' in p['qual'] for p in policies)
 flags=sql("select json_agg(json_build_object('table',c.relname,'rls',c.relrowsecurity,'forceRls',c.relforcerowsecurity)) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='paper_trading' and c.relname in ('decision_research_source','decision_source_link')")
 assert all(p['rls'] and p['forceRls'] for p in flags)
 immutable=sql("select json_build_object('sourceUpdate',has_table_privilege('aiquant_tenant','paper_trading.decision_research_source','UPDATE'),'sourceDelete',has_table_privilege('aiquant_tenant','paper_trading.decision_research_source','DELETE'),'linkUpdate',has_table_privilege('aiquant_tenant','paper_trading.decision_source_link','UPDATE'))");assert not any(immutable.values())
 page=http('/paper/decisions');entry=http(re.search(r'src="([^"]*/assets/index-[^"]+\.js)"',page)[1]);desk=re.search(r'DecisionDeskView-[A-Za-z0-9_-]+\.js',entry)[0];research=re.search(r'InstrumentResearchView-[A-Za-z0-9_-]+\.js',entry)[0]
 assert '研究原文与来源版本' in http('/assets/'+desk)
 assert '确认归属并导入' in http('/assets/'+research)
 for path in ['/api/v1/paper/decisions','/api/v1/paper/decisions/','/api/v1/paper/decisions/research/sources/00000000-0000-4000-8000-000000000001']:
  try:http(path);raise AssertionError('Anonymous private read accepted')
  except urllib.error.HTTPError as error:assert error.code==401
 counts=sql("select json_build_object('sources',(select count(*) from paper_trading.decision_research_source),'links',(select count(*) from paper_trading.decision_source_link),'enabledMonitorJobs',(select count(*) from market.live_monitor where enabled))")
 receipt={'scope':'READ_ONLY_PRODUCTION_CHECK_NO_SYNTHETIC_DATA_INSERTED','verifiedAtUtc':datetime.now(timezone.utc).isoformat(),'result':'PASSED','health':health,'tables':tables,'migration':version,'policies':policies,'flags':flags,'immutableGrants':immutable,'currentCounts':counts,'frontendBundles':[desk,research],'images':{s:command('docker','inspect','--format','{{.Image}}','ai-quant-'+s+'-1') for s in SERVICES}}
 (OUT/'deployment.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps({'result':'PASSED','health':health,'migration':version,'allOriginalIdsPreserved':True,'currentCounts':counts}))
if __name__=='__main__':main()
