"""Verify deployed comparison API/static assets and retain one research example.

Does not create judgments, orders, or notifications. Optional prior monitor
capture verifies that the upgrade kept that task's immutable evidence intact.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import urllib.request
import uuid

from test_chanlun_comparison_protocol import DEFAULT_RUNS


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--before-monitor',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--runs',nargs='+',default=DEFAULT_RUNS);p.add_argument('--comparison',type=uuid.UUID,help='Reuse an existing example instead of creating another');args=p.parse_args()
    base='http://localhost:8088'
    def raw(path):
        with urllib.request.urlopen(base+path,timeout=120) as response:assert response.status==200;return response.read().decode('utf-8')
    def call(path,body=None):
        req=urllib.request.Request(base+'/api/chanlun/v1'+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=120) as response:assert response.status==200;return json.load(response)
    html=raw('/chanlun/compare');index=re.search(r'src="([^"]+\.js)"',html).group(1);javascript=raw(index)
    chunk=re.search(r'CompareView-[A-Za-z0-9_-]+\.js',javascript).group(0);assert '引擎分歧研究' in raw('/assets/'+chunk)
    request={'clientRequestId':str(uuid.uuid4()),'runIds':[str(uuid.UUID(id)) for id in args.runs],'layer':'BI','projection':'WITH_CONFIRMATION','confirmedOnly':False}
    if args.comparison:
        value=call('/comparisons/'+str(args.comparison));assert value['request']['runIds']==request['runIds'];request=value['request']
    else:value=call('/comparisons',request)
    assert value['status']=='SUCCEEDED',value
    id=value['id'];report=value['report'];assert call('/comparisons',request)['id']==id
    assert call('/comparisons/'+id)['report']==report
    index=report['firstDifference']['observedIndex'];detail=call(f'/comparisons/{id}/at/{index}')
    assert all(len(f['analysis']['bars'])==index+1==f['analysis']['observedBars'] for f in detail['frames'])
    assert detail['date']==report['firstDifference']['date']
    checks=['deployed_route_and_comparison_chunk_http_200','real_three_engine_archived_comparison','first_difference_prefix_bounds','idempotence_and_frozen_restore']
    if args.before_monitor:
        previous=json.loads(args.before_monitor.read_text(encoding='utf-8'));current=call('/monitors/'+previous['id'])
        assert current['id']==previous['id'] and current['observedBars']==previous['observedBars'] and current['profileHash']==previous['profileHash']
        assert current['events']==previous['events']
        assert current['analysis']==previous['analysis']
        checks.append('existing_monitor_current_head_and_events_preserved')
    def command(*parts):return subprocess.run(parts,check=True,capture_output=True,text=True,encoding='utf-8').stdout.strip()
    version=command('docker','compose','-f','infrastructure/docker-compose.yml','exec','-T','postgres','psql','-U','aiquant','-d','aiquant','-At','-c',"select max(version::int) from chanlun.flyway_schema_history where success and version is not null");assert version=='7'
    health={name:command('docker','inspect','--format','{{.State.Health.Status}}','ai-quant-'+name+'-1') for name in ('frontend','chanlun-service','gateway-service','algorithm-service')};assert all(v=='healthy' for v in health.values()),health
    result={'status':'PASS','verifiedAt':datetime.now(timezone.utc).isoformat(),'scope':'DEPLOYED_HTTP_STATIC_API_AND_SCHEMA_UPGRADE','schemaVersion':int(version),'health':health,'comparisonId':id,'link':base+f'/chanlun/compare?comparison={id}&at={index}','firstDifference':{'index':index,'bars':index+1,'date':detail['date']},'sourceRunIds':request['runIds'],'datasetHash':report['datasetHash'],'checks':checks,'retainedExample':True,'judgmentsOrOrdersCreated':False,'detailSha256':hashlib.sha256(json.dumps(detail,sort_keys=True,ensure_ascii=False).encode()).hexdigest()}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
