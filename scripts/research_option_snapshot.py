"""Read-only option chain collection through the running primary provider, no orders."""
import hashlib,json,re,subprocess,time
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/history/options-study-2026-11-07'
def get(path):
    code="import urllib.request;print(urllib.request.urlopen("+repr('http://127.0.0.1:8000'+path)+",timeout=30).read().decode())"
    return json.loads(subprocess.check_output(['docker','exec','ai-quant-algorithm-service-1','python','-c',code],text=True,encoding='utf-8'))
def main():
    from urllib.parse import urlencode
    OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/'collection.json').exists():raise SystemExit('Completed collection exists; do not overwrite')
    catalog=get('/api/v1/options/catalog');(OUT/'catalog.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding='utf-8')
    inventory=json.loads((ROOT/'docs/research/data/multifactor-chan-2026-11-07/results.json').read_text(encoding='utf-8'))['inventory']
    selected=[];budget=0
    for root in ('rb','cu','au','ru','sc','m','y','p','i','pp','l','c','SA','MA','TA','CF','SR','OI'):
        historical=next((i for i in inventory if i['root'].split('.')[-1].lower()==root.lower()),None)
        options=[c for c in catalog['chains'] if re.fullmatch(r'[A-Z]+\.'+root+r'\d+',c['underlyingSymbol'])]
        options=[c for c in options if 14<(datetime.fromisoformat(c['expiry'])-datetime.now(timezone.utc)).total_seconds()/86400<100 and c['contractCount']<=180]
        options.sort(key=lambda c:(c['underlyingSymbol']!=(historical or {}).get('contract'),c['expiry']))
        if not options:continue
        chain=options[0]
        if budget+chain['contractCount']>1450:continue
        budget+=chain['contractCount'];selected.append({'root':root,'chain':chain,'historical':historical})
    protocol={'collectedAt':datetime.now(timezone.utc).isoformat(),'mode':'Existing SDK worker through read-only HTTP; no order calls',
              'selection':'18 fixed active roots; nearest14-100day expiry preferring identical frozen actual contract; <=180 contracts/chain and total<=1450 metadata contracts',
              'selected':selected,'rateAssumption':.02,'dividendAssumption':0,'quoteStatus':'Preserve exchange timestamps; weekend observations are cached, not executable live prices.'}
    (OUT/'protocol.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    for i,item in enumerate(selected):
        path='/api/v1/options/chain?'+urlencode({'chainId':item['chain']['id'],'rate':.02,'dividend':0})
        get(path) # Queue subscription in existing feed worker.
        print(json.dumps({'stage':'QUEUED','root':item['root'],'contracts':item['chain']['contractCount']}),flush=True)
    # Bounded polling gives the worker time; missing data stays missing.
    snapshots={}
    for attempt in range(4):
        missing=0
        for item in selected:
            path='/api/v1/options/chain?'+urlencode({'chainId':item['chain']['id'],'rate':.02,'dividend':0})
            data=get(path);snapshots[item['root']]=data
            if not data.get('underlying',{}).get('dataTimestamp'):missing+=1
        print(json.dumps({'stage':'READ','attempt':attempt+1,'missingUnderlying':missing}),flush=True)
        if not missing:break
        if attempt<3:time.sleep(8)
    manifest=[]
    for root,data in snapshots.items():
        path=OUT/(root+'-chain.json');path.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
        rows=data['contracts'];manifest.append({'root':root,'file':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
          'underlying':data['chain']['underlyingSymbol'],'status':data['dataStatus'],'message':data.get('message'),
          'contracts':len(rows),'quoted':sum(bool(r.get('dataTimestamp')) for r in rows),'twoSided':sum(bool(r.get('bidPrice') and r.get('askPrice') and r.get('bidVolume') and r.get('askVolume')) for r in rows)})
    (OUT/'collection.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'stage':'COMPLETE','chains':len(manifest),'metadataContracts':budget,'observed':manifest},ensure_ascii=True),flush=True)
if __name__=='__main__':main()
