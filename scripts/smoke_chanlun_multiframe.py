"""Actual primary multi-timeframe capture, prefix bounds and frozen restore.

Only immutable research observations are created. No orders or notifications.
"""
import argparse
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request
import uuid


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--symbol',default='FU2701');p.add_argument('--cleanup',action='store_true');p.add_argument('--output',type=Path);args=p.parse_args()
    base='http://localhost:8088/api/chanlun/v1/multiframe';requests=[];report=None
    def call(path='',body=None,status=200):
        req=urllib.request.Request(base+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req,timeout=120) as r:assert r.status==status;return json.load(r)
        except urllib.error.HTTPError as exc:
            if exc.code!=status:raise AssertionError((exc.code,exc.read().decode())) from exc
            return None
    def create(frames,as_of=None):
        body={'clientRequestId':str(uuid.uuid4()),'symbol':args.symbol,'frames':frames,'asOf':as_of};requests.append(body['clientRequestId'])
        for _ in range(60):
            r=call(body=body)
            if r['status'] in ('SUCCEEDED','FAILED'):break
            time.sleep(1)
        assert r['status']=='SUCCEEDED',(r['status'],r['error'])
        assert call('/'+r['id'])['report']==r['report']==call(body=body)['report']
        call(body={**body,'frames':'TRIPLE' if frames=='PAIR' else 'PAIR'},status=409)
        result=r['report'];cutoff=datetime.fromisoformat(result['asOf'])
        assert result['executable'] is False and len(result['frames'])==(2 if frames=='PAIR' else 3)
        for f in result['frames']:
            a=f['analysis'];bars=a['bars'];assert len(bars)==a['observedBars']>=50
            assert a['symbol']==args.symbol and all(b['contract']==args.symbol for b in bars)
            assert all(datetime.fromisoformat(b['sealedByTimestamp'])<=cutoff for b in bars)
            assert all(b['providerIndex']==a['providerIndex']+1 for a,b in zip(bars,bars[1:]))
            assert all(s['endIndex']<=s['observedIndex']<len(bars) for s in a['structures'])
        return r
    try:
        pair=create('PAIR');triple=create('TRIPLE')
        low=next(f for f in triple['report']['frames'] if f['frequency']=='MIN5')
        earlier=low['analysis']['bars'][-120]['sealedByTimestamp'];past=create('TRIPLE',earlier)
        assert datetime.fromisoformat(past['report']['asOf'])==datetime.fromisoformat(earlier)
        for f in past['report']['frames']:
            latest=next(x for x in triple['report']['frames'] if x['frequency']==f['frequency'])
            assert f['analysis']['observedBars']<=latest['analysis']['observedBars']
        call(body={'clientRequestId':str(uuid.uuid4()),'symbol':args.symbol,'frames':'PAIR','asOf':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()},status=400)
        report={'status':'PASS','verifiedAt':datetime.now(timezone.utc).isoformat(),'scope':'REAL_TQSDK_SERIALS_SUCCESSOR_BOUND_RECONSTRUCTION_CLOSED_MARKET',
            'checks':['independent_pair_and_triple_serials','every_bar_sealed_by_common_cutoff','structures_rebuilt_on_prefix',
                      'earlier_cutoff_has_no_later_input','frozen_restore_and_idempotence','changed_request_conflict','future_cutoff_rejected'],
            'latestAsOf':triple['report']['asOf'],'earlierAsOf':past['report']['asOf'],
            'frames':{f['frequency']:{'bars':f['analysis']['observedBars'],'firstProviderIndex':f['firstProviderIndex'],'lastProviderIndex':f['lastProviderIndex'],'lastSealedBy':f['lastSealedBy'],'receiptAt':f['source']['receiptAt']} for f in triple['report']['frames']},
            'observationIds':[pair['id'],triple['id'],past['id']],'cleanupRequested':args.cleanup,'cleanupCompleted':False}
    finally:
        if args.cleanup and requests:
            ids=','.join("'"+str(uuid.UUID(r))+"'" for r in requests)
            subprocess.run(['docker','compose','-f','infrastructure/docker-compose.yml','exec','-T','postgres','psql','-U','aiquant','-d','aiquant','-v','ON_ERROR_STOP=1','-c',f'delete from chanlun.multiframe_run where client_request_id in ({ids})'],check=True,capture_output=True,text=True,encoding='utf-8')
            if report:report['cleanupCompleted']=True
    if args.output:args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
