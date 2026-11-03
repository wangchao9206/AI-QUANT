"""Check actual cost-lab persistence/idempotence. Never creates orders or notes."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://localhost:8088')
    parser.add_argument('--cleanup', action='store_true')
    parser.add_argument('--output', type=Path)
    args=parser.parse_args()
    if args.cleanup and urllib.parse.urlsplit(args.base_url).hostname not in ('localhost','127.0.0.1'):
        parser.error('Cleanup only supports local Docker verification')
    base=args.base_url.rstrip('/')+'/api/chanlun/v1/lab'
    request_id=str(uuid.uuid4())
    report=None

    def call(path='', body=None, status=200):
        req=urllib.request.Request(base+path, data=json.dumps(body).encode() if body else None,
                                  headers={'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                assert response.status==status
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code!=status:
                raise AssertionError((exc.code,exc.read().decode())) from exc
            return None

    try:
        body={'clientRequestId':request_id, 'group':'ALL', 'initialCash':1000000}
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses=list(pool.map(lambda _:call(body=body),range(2)))
        identifier=responses[0]['id']
        assert all(r['id']==identifier for r in responses)
        value=call('/'+identifier)
        for _ in range(30):
            if value['status']!='RUNNING':break
            time.sleep(1);value=call('/'+identifier)
        assert value['status']=='SUCCEEDED', value
        result=value['report']
        assert result['executable'] is False and len(result['variants'])==5
        assert len(result['candidateTape'])==18
        for v in result['variants']:
            m=v['metrics']
            assert abs(m['netPnl']-sum(t['netPnl'] for t in v['trades']))<1e-5
            assert abs(m['initialCash']+m['netPnl']-m['finalEquity'])<1e-5
            assert all(t['entryIndex']>t['confirmedIndex'] for t in v['trades'])
        repeat=call(body=body)
        restored=call('/'+identifier)
        assert repeat['report']==restored['report']==result
        call(body={**body,'group':'THIRD'},status=409)
        call(body={**body,'clientRequestId':str(uuid.uuid4()),'initialCash':123456},status=400)
        report={'status':'PASS','verifiedAt':datetime.now(timezone.utc).isoformat(),'experimentId':identifier,'clientRequestId':request_id,
            'configHash':result['configHash'],'profileHash':result['config']['profileHash'],
            'checks':['concurrent_request_dedup','changed_request_conflict','frozen_restore',
                      'five_scenarios_reconcile','next_bar_execution','fixed_config_validation'],
            'metrics':{v['id']:v['metrics'] for v in result['variants']},
            'cleanupRequested':args.cleanup,'cleanupCompleted':False}
    finally:
        if args.cleanup:
            # Exact randomly owned request only; no user experiments, judgments or orders.
            command=['docker','compose','-f','infrastructure/docker-compose.yml','exec','-T','postgres',
                'psql','-U','aiquant','-d','aiquant','-v','ON_ERROR_STOP=1','-Atc',
                f"delete from chanlun.lab_experiment where client_request_id='{uuid.UUID(request_id)}' returning id"]
            cleaned=subprocess.run(command,check=True,capture_output=True,text=True)
            if report:
                assert report['experimentId'] in cleaned.stdout
                report['cleanupCompleted']=True
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
