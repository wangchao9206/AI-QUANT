"""Real Java/PostgreSQL/Chan workflow protocol, isolated from the deployed system."""
import base64
from datetime import datetime, timezone
import hashlib
import hmac
import json
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

ROOT=Path(__file__).resolve().parents[1]
TOKEN='isolated-chan-workflow-internal-secret-only'
SUFFIX=uuid.uuid4().hex[:10]
NETWORK='aq-chan-check-'+SUFFIX
DB=NETWORK+'-db';PEER=NETWORK+'-peer';APP=NETWORK+'-paper'
containers=[]


def docker(*args):
    return subprocess.check_output(['docker',*args],text=True,encoding='utf-8').strip()


def start(name,*args):
    docker('run','-d','--name',name,'--network',NETWORK,*args);containers.append(name)


def wait(check,seconds=150):
    limit=time.monotonic()+seconds
    while time.monotonic()<limit:
        if APP in containers and docker('inspect',APP,'--format','{{.State.Status}}')=='exited':
            raise RuntimeError('Isolated paper service exited during startup')
        try:
            value=check()
            if value:return value
        except Exception:pass
        time.sleep(1)
    raise AssertionError('Isolated service readiness timed out')


def signed(tenant='00000000-0000-0000-0000-000000000001'):
    payload={'tenantId':tenant,'userId':'10000000-0000-0000-0000-000000000001','role':'OWNER','expiresAt':int(time.time())+30}
    raw=base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')
    signature=base64.urlsafe_b64encode(hmac.new(TOKEN.encode(),raw.encode(),hashlib.sha256).digest()).decode().rstrip('=')
    return raw+'.'+signature


def call(path,body=None,expected=200,tenant=None,base=None,timeout=90):
    req=urllib.request.Request((base or BASE)+path,data=json.dumps(body).encode() if body is not None else None,
        headers={'Content-Type':'application/json','X-Aiquant-Identity':signed(tenant) if tenant else signed()})
    try:
        with urllib.request.urlopen(req,timeout=timeout) as response:code,value=response.status,json.load(response)
    except urllib.error.HTTPError as error:code,value=error.code,json.load(error)
    assert code==expected,(path,code,value)
    return value


def definition(pins):
    nodes=[{'id':'market','type':'MARKET'},{'id':'chan','type':'CHAN_SIGNAL','params':{**pins,'group':'ALL'}},
           {'id':'risk','type':'RISK','params':{'lots':1,'stopLossAtr':2,'takeProfitAtr':3}}]
    edges=[{'id':'source','source':'market','sourcePort':'bars','target':'chan','targetPort':'market'}]
    for action,port in [('BUY','buy'),('SELL','sell'),('FLATTEN','close')]:
        nodes.append({'id':action,'type':'ACTION','params':{'action':action}})
        edges.extend([{'id':'signal-'+action,'source':'chan','sourcePort':port,'target':action,'targetPort':'condition'},
                      {'id':'risk-'+action,'source':'risk','sourcePort':'risk','target':action,'targetPort':'risk'}])
    return {'schemaVersion':2,'nodes':nodes,'edges':edges}


try:
    docker('network','create',NETWORK)
    start(DB,'--memory','512m','--tmpfs','/var/lib/postgresql/data:rw,size=512m','-e','POSTGRES_DB=paper_test',
          '-e','POSTGRES_USER=paper_test','-e','POSTGRES_PASSWORD=isolated-test-only','postgres:17.6-alpine3.22')
    wait(lambda:subprocess.run(['docker','exec',DB,'pg_isready','-U','paper_test','-d','paper_test'],capture_output=True).returncode==0)
    start(PEER,'--memory','512m','-p','127.0.0.1::8011','--mount',f'type=bind,source={ROOT / "tests/integration/chanlun_workflow_peer.py"},target=/app/protocol_peer.py,readonly',
          'ai-quant-algorithm-service','python','protocol_peer.py')
    peerPort=json.loads(docker('inspect',PEER))[0]['NetworkSettings']['Ports']['8011/tcp'][0]['HostPort']
    peerUrl='http://127.0.0.1:'+peerPort
    fixture=wait(lambda:call('/fixture',base=peerUrl,timeout=3))
    start(APP,'--memory','768m','--read-only','--tmpfs','/tmp:rw,size=128m','-p','127.0.0.1::8083',
          '-e',f'DATABASE_URL=jdbc:postgresql://{DB}:5432/paper_test','-e','DATABASE_USERNAME=paper_test','-e','DATABASE_PASSWORD=isolated-test-only',
          '-e',f'SPRING_FLYWAY_URL=jdbc:postgresql://{DB}:5432/paper_test','-e','SPRING_FLYWAY_USER=paper_test','-e','SPRING_FLYWAY_PASSWORD=isolated-test-only',
          '-e','SPRING_FLYWAY_SCHEMAS=paper_trading','-e','DATABASE_SCHEMA=paper_trading',
          '-e','IDENTITY_INTERNAL_SECRET='+TOKEN,'-e','NACOS_ENABLED=false','-e','ROCKETMQ_ENABLED=false','-e','SERVER_PORT=8083',
          '-e','ALGORITHM_SERVICE_URL=http://'+PEER+':8011','-e','MARKET_SERVICE_URL=http://'+PEER+':8011','ai-quant-paper-trading-service')
    appPort=json.loads(docker('inspect',APP))[0]['NetworkSettings']['Ports']['8083/tcp'][0]['HostPort']
    BASE='http://127.0.0.1:'+appPort
    wait(lambda:call('/actuator/health/readiness',timeout=3).get('status')=='UP')
    print('Isolated Java/PostgreSQL/real Chan engine ready',flush=True)
    graph=definition(call('/api/v1/paper/workflows/chan-profile'))
    draft=call('/api/v1/paper/workflows',{'clientRequestId':str(uuid.uuid4()),'name':'isolated real Chan protocol','description':'isolated verification','definition':graph})
    publish={'expectedRevision':1,'clientRequestId':str(uuid.uuid4())}
    version=call('/api/v1/paper/workflows/'+draft['id']+'/publish',publish)
    assert version['engineVersion']=='workflow-daily-v2'
    assert call('/api/v1/paper/workflows/'+draft['id']+'/publish',publish)['id']==version['id']
    path='/api/v1/paper/workflows/versions/'+version['id']+'/shadows'
    command={'clientRequestId':str(uuid.uuid4()),'symbol':fixture['symbol'],'asOf':fixture['asOf'],'direction':0}
    shadow=call(path,command)
    assert shadow['signal'] in ('BUY','SELL'),shadow['signal']
    assert call(path,command)['id']==shadow['id']
    call(path,{**command,'direction':1},409)
    call('/api/v1/paper/workflows/shadows/'+shadow['id'],expected=404,tenant='20000000-0000-0000-0000-000000000002')
    account={'name':'isolated Chan account','mode':'HISTORICAL','symbol':fixture['symbol'],'startDate':fixture['startDate'],'endDate':fixture['endDate'],
             'initialCash':1000000,'marginRate':.12,'feeRate':.0001,'slippageTicks':1,'maxParticipationRate':.1,'autoRoll':True,
             'strategyId':'WORKFLOW','workflowVersionId':version['id'],'workflowShadowId':shadow['id']}
    call('/api/v1/paper/sessions',{**account,'mode':'LIVE'},400)
    call('/api/v1/paper/sessions',{k:v for k,v in account.items() if k!='workflowShadowId'},400)
    call('/api/v1/paper/sessions',{**account,'symbol':'RB0'},409)
    otherVersion=call('/api/v1/paper/workflows/'+draft['id']+'/publish',{**publish,'clientRequestId':str(uuid.uuid4())})
    call('/api/v1/paper/sessions',{**account,'workflowVersionId':otherVersion['id']},409)
    session=call('/api/v1/paper/sessions',account)
    assert session['workflowShadowId']==shadow['id'] and session['orderCount']==0
    advanced=call('/api/v1/paper/sessions/'+session['id']+'/advance',{'steps':1})
    assert advanced['fillCount']>=1,advanced.get('executionMessage')
    decision=advanced['strategyDecisions'][0]
    evidence=call('/api/v1/paper/sessions/'+session['id']+'/strategy-evidence?'+urllib.parse.urlencode({'asOf':decision['signalTime']}))
    first=next(n for n in shadow['nodeTrace'] if n['type']=='CHAN_SIGNAL')['value']
    actual=next(n for n in evidence['nodeTrace'] if n['type']=='CHAN_SIGNAL')['value']
    assert first==actual,'Frozen shadow and ledger decision disagree'
    assert all(datetime.fromisoformat(b['timestamp'].replace('Z','+00:00'))<=datetime.fromisoformat(decision['signalTime'].replace('Z','+00:00')) for b in evidence['inputSnapshot']['signalBars'])
    assert any(n['type']=='SHADOW_REFERENCE' for n in evidence['nodeTrace'])
    call('/api/v1/paper/sessions/'+session['id']+'/strategy-evidence?'+urllib.parse.urlencode({'asOf':decision['signalTime']}),expected=400,tenant='20000000-0000-0000-0000-000000000002')
    completed=call('/api/v1/paper/sessions/'+session['id']+'/advance',{'steps':100})
    assert completed['status']=='COMPLETED'
    assert any(n['value']=='NO_SUCCESSOR_BAR' for n in completed['strategyDecisions'][0]['nodeTrace'])
    poor=call('/api/v1/paper/sessions',{**account,'initialCash':1000})
    poor=call('/api/v1/paper/sessions/'+poor['id']+'/advance',{'steps':1})
    assert poor['fillCount']==0 and any(o['status']=='REJECTED' for o in poor['orders'])
    call('/fixture-control',{'zeroVolume':True},base=peerUrl)
    dry=call('/api/v1/paper/sessions',account)
    dry=call('/api/v1/paper/sessions/'+dry['id']+'/advance',{'steps':1})
    assert dry['fillCount']==0 and any(o['status']=='CANCELLED' and o['rejectionReason'] for o in dry['orders'])
    assert any(n['value']=='NEXT_BAR_LIQUIDITY' for n in dry['strategyDecisions'][0]['nodeTrace'])
    call('/fixture-control',{'noAtr':True},base=peerUrl)
    noAtrShadow=call(path,{**command,'clientRequestId':str(uuid.uuid4())})
    noAtr=call('/api/v1/paper/sessions',{**account,'workflowShadowId':noAtrShadow['id']})
    noAtr=call('/api/v1/paper/sessions/'+noAtr['id']+'/advance',{'steps':1})
    assert noAtr['orderCount']==0 and any(n['value']=='MISSING_DELIVERY_ATR' for n in noAtr['strategyDecisions'][0]['nodeTrace'])
    docker('stop',PEER)
    docker('restart',APP)
    appPort=json.loads(docker('inspect',APP))[0]['NetworkSettings']['Ports']['8083/tcp'][0]['HostPort']
    BASE='http://127.0.0.1:'+appPort
    wait(lambda:call('/actuator/health/readiness',timeout=3).get('status')=='UP')
    assert call('/api/v1/paper/workflows/shadows/'+shadow['id'])==shadow
    assert call('/api/v1/paper/sessions/'+session['id']+'/strategy-evidence?'+urllib.parse.urlencode({'asOf':decision['signalTime']}))==evidence
    report={'status':'PASSED','isolated':True,'realPinnedArchive':True,'candidateIndex':fixture['candidateIndex'],
            'checks':['v2 publish and retry','shadow retry and conflict','cross-tenant denial','live/missing/wrong-symbol rejection',
                      'no orders before explicit advance','real native candidate and next-bar ledger fill','identical shadow/decision prefix evidence',
                      'no future bars in evidence','terminal bar rejected without orders','insufficient margin rejected',
                      'synthetic zero-volume order expires after first eligible bar','synthetic missing ATR blocks orders',
                      'saved shadow and decision readable after restart with engine offline'],
            'fills':advanced['fillCount'],'observedSignal':shadow['signal'],'recordedAt':datetime.now(timezone.utc).isoformat()}
    output=ROOT/'.test-tmp/optimization-bridge-protocol.json';output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2),flush=True)
except Exception:
    for name in containers:
        if name!=DB:
            logs=subprocess.run(['docker','logs','--tail','160',name],capture_output=True,text=True,encoding='utf-8')
            print(name,logs.stdout,logs.stderr,flush=True)
    raise
finally:
    for name in reversed(containers):subprocess.run(['docker','rm','-f',name],capture_output=True)
    subprocess.run(['docker','network','rm',NETWORK],capture_output=True)
