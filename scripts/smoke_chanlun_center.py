"""Exercise the deployed prefix API. Creates analysis records, never orders or judgments."""
import argparse
import json
import urllib.error
import urllib.request
import uuid

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--base-url',default='http://localhost:8088')
args=parser.parse_args()
base=args.base_url.rstrip('/')+'/api/chanlun/v1'


def call(path,body=None):
    req=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,
                               headers={'Content-Type':'application/json','Accept':'application/json'})
    with urllib.request.urlopen(req,timeout=120) as response:return json.load(response)


dataset=call('/datasets')[0]
results=[]
for engine in ('native','chanpy','czsc','baseline'):
    command={'clientRequestId':str(uuid.uuid4()),'engineId':engine,'datasetId':dataset['id'],'observedBars':501}
    run=call('/runs',command)
    assert run['status']=='SUCCEEDED',run
    repeated=call('/runs',command)
    assert repeated['id']==run['id'],'Retry created a duplicate analysis'
    result=call(f"/runs/{run['id']}/structures")
    assert len(result['bars'])==501 and result['bars'][-1]['date']==result['observedAsOfDate']
    assert result['datasetHash']==dataset['sha256'] and result['profile']['implementationHash']
    assert result['executable'] is False
    assert all(s['endIndex']<501 and s['eligibleAt'] is None for s in result['structures'])
    if result['structures']:
        item=result['structures'][-1]
        history=call(f"/runs/{run['id']}/events?structureId={item['id']}")
        assert history and all(e['observedDate']<=result['observedAsOfDate'] for e in history)
        assert len({e['eventSeq'] for e in history})==len(history)
    try:
        call('/runs',{**command,'observedBars':502})
        raise AssertionError('Changed request with the same key was accepted')
    except urllib.error.HTTPError as error:
        assert error.code==409,error.code
    results.append({'engine':engine,'runId':run['id'],'observedDate':result['observedAsOfDate'],'counts':result['counts']})
try:
    call('/runs',{'clientRequestId':str(uuid.uuid4()),'engineId':'pro','datasetId':dataset['id'],'observedBars':501})
    raise AssertionError('Unsupported pro engine was accepted')
except urllib.error.HTTPError as error:
    assert error.code==400,error.code
print(json.dumps({'status':'PASSED','prefixAndRetryChecks':results},ensure_ascii=False,indent=2))
