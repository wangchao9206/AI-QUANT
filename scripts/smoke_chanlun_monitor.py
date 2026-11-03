"""Verify primary sealed candles on local deployment; no orders/notifications.

Creates one exact-owned monitor and optionally cleans only that task and evidence.
"""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import subprocess
import time
import urllib.request
import uuid


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--symbol',default='FU2701');p.add_argument('--frequency',default='MIN5',choices=['MIN5','MIN30','DAY']);p.add_argument('--cleanup',action='store_true');p.add_argument('--output',type=Path);args=p.parse_args()
    base='http://localhost:8088/api/chanlun/v1/monitors';request_id=str(uuid.uuid4());identifier=None;report=None
    def call(path='',body=None):
        request=urllib.request.Request(base+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(request,timeout=120) as response:return json.load(response)
    try:
        body={'clientRequestId':request_id,'title':'TEST-PRIMARY-MONITOR-'+uuid.uuid4().hex,'symbol':args.symbol,'frequency':args.frequency}
        initial=call(body=body);identifier=initial['id'];assert call(body=body)['id']==identifier
        for _ in range(60):
            value=call('/'+identifier+'/check',{})
            if value['observedBars']>=50:break
            time.sleep(1)
        assert value['observedBars']>=50,(value['status'],value['error'])
        assert value['source']['source']=='TQSDK_PRIMARY_SERIAL' and value['source']['closeProof']=='SUCCESSOR_OBSERVED'
        analysis=value['analysis'];bars=analysis['bars']
        assert all(b['contract']==args.symbol for b in bars)
        assert all(b['providerIndex']==a['providerIndex']+1 for a,b in zip(bars,bars[1:]))
        checked=datetime.fromisoformat(value['source']['checkedAt'])
        assert all(datetime.fromisoformat(b['timestamp'])<=checked for b in bars)
        assert value['events'] and all(e['inboxState']!='NEW' for e in value['events'])
        event=value['events'][0];frozen=call(f"/{identifier}/events/{event['eventSeq']}")
        assert frozen['analysis']['observedBars']==event['payload']['observedIndex']+1
        assert len(frozen['analysis']['structures'])==1 and frozen['analysis']['bars'][-1]['index']==event['payload']['observedIndex']
        original_events=value['events'];again=call('/'+identifier+'/check',{})
        if again['observedBars']==value['observedBars']:assert again['events']==original_events
        report={'status':'PASS','verifiedAt':datetime.now(timezone.utc).isoformat(),'scope':'REAL_TQSDK_PRIMARY_SEALED_BARS_CLOSED_MARKET',
            'monitorId':identifier,'symbol':args.symbol,'frequency':args.frequency,'state':value['status'],
            'observedBars':len(bars),'firstBar':bars[0]['timestamp'],'lastSealedBar':bars[-1]['timestamp'],
            'firstProviderIndex':bars[0]['providerIndex'],'lastProviderIndex':bars[-1]['providerIndex'],
            'receiptAt':value['source']['receiptAt'],'profileHash':value['profileHash'],
            'recentEvents':len(value['events']),'checks':['primary_source_no_fallback','successor_sealed_no_future_bar',
                'provider_index_continuity','bootstrap_not_fresh_alert','frozen_event_prefix','repeat_poll_dedup'],
            'cleanupRequested':args.cleanup,'cleanupCompleted':False}
    finally:
        if args.cleanup and identifier:
            call('/'+identifier+'/control',{'enabled':False})
            sql=f"""begin;
            delete from chanlun.monitor_review where monitor_id='{uuid.UUID(identifier)}';
            update chanlun.monitor set latest_snapshot_id=null where id='{uuid.UUID(identifier)}' and client_request_id='{uuid.UUID(request_id)}';
            delete from chanlun.monitor_event where monitor_id='{uuid.UUID(identifier)}';
            delete from chanlun.monitor_snapshot where monitor_id='{uuid.UUID(identifier)}';
            delete from chanlun.monitor where id='{uuid.UUID(identifier)}' and client_request_id='{uuid.UUID(request_id)}';commit;"""
            subprocess.run(['docker','compose','-f','infrastructure/docker-compose.yml','exec','-T','postgres','psql','-U','aiquant','-d','aiquant','-v','ON_ERROR_STOP=1','-c',sql],check=True,capture_output=True,text=True)
            if report:report['cleanupCompleted']=True
    if args.output:args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
