"""Real Docker API smoke check scoped to the disposable QA author/tenant."""
import json,uuid
from pathlib import Path
import requests

ROOT=Path(__file__).resolve().parents[1]
qa=json.loads((ROOT/'.test-tmp/manual-replay-qa-identity.json').read_text())
base='http://127.0.0.1:18080'
s=requests.Session();s.headers['Origin']='http://localhost:8088'
def call(method,path,body=None,expected=200):
    csrf=s.cookies.get('aq_csrf')
    if csrf:s.headers['X-CSRF-Token']=csrf
    r=s.request(method,base+path,json=body,timeout=40)
    assert r.status_code==expected,(method,path,r.status_code,r.text[:500])
    return r.json() if r.content else None

call('POST','/api/v1/auth/login',dict(identifier=qa['username'],password=qa['password']))
catalog=call('GET','/api/v1/paper/intraday/catalog');assert catalog['symbols'][0]['symbol']=='FG701'
session=call('POST','/api/v1/paper/sessions',dict(name='Docker API isolated minute check',mode='HISTORICAL',symbol='FG701',
    startDate='2026-10-28',endDate='2026-10-28',initialCash=100000,marginRate=.12,feeRate=.0001,slippageTicks=1,
    maxParticipationRate=.1,autoRoll=False,strategyId='MANUAL',strategyLots=1,barSeconds=60,stopLossTicks=0,intradayOnly=True))
sid=session['id'];prefix=f'/api/v1/paper/sessions/{sid}'
assert session['barSeconds']==60 and session['totalBars']==345
try:
    call('POST',prefix+'/orders',dict(clientOrderId=str(uuid.uuid4()),side='BUY',offset='OPEN',orderType='MARKET',quantity=1))
    session=call('POST',prefix+'/advance',dict(steps=1));assert session['position']['lots']==1
    fill=session['fills'][0];note=prefix+f"/fills/{fill['id']}/note"
    call('POST',note,dict(content='真实Docker接口验收：等待信号，记录感受。',version=0))
    assert call('GET',note)['version']==1
    call('POST',note,dict(content='stale',version=0),expected=409)
    chart=call('GET',prefix+'/chart');assert chart['barSeconds']==60
    assert len(chart['fills'])==1
    call('POST',prefix+'/orders',dict(clientOrderId=str(uuid.uuid4()),side='SELL',offset='CLOSE',orderType='MARKET',quantity=1))
    session=call('POST',prefix+'/advance',dict(steps=1));assert session['position']['lots']==0 and len(session['fills'])==2
    print('PASS: real Docker auth, minute archive, next-bar open/close, private note save/read and stale revision rejection.')
finally:
    call('DELETE',prefix,expected=204)
