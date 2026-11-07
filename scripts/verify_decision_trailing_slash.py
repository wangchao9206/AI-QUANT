"""Read-only internal route probe with a short-lived random empty-workspace identity.

No production user/session is impersonated, created or read. Never print signing material.
"""
import base64,hashlib,hmac,json,subprocess,time,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    values={}
    for line in (ROOT/'infrastructure/.env').read_text(encoding='utf-8-sig').splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            key,value=line.split('=',1);values[key.strip()]=value.strip().strip(chr(34)).strip(chr(39))
    secret=values['IDENTITY_INTERNAL_SECRET']
    payload=base64.urlsafe_b64encode(json.dumps({'userId':str(uuid.uuid4()),'tenantId':str(uuid.uuid4()),'role':'VIEWER','permissions':['market.read','paper.read'],'expiresAt':int(time.time())+30},separators=(',',':')).encode()).decode().rstrip('=')
    token=payload+'.'+base64.urlsafe_b64encode(hmac.new(secret.encode(),payload.encode(),hashlib.sha256).digest()).decode().rstrip('=')
    checks=[]
    for path in ['/api/v1/paper/decisions','/api/v1/paper/decisions/']:
        try:
            result=subprocess.run(['docker','exec','ai-quant-paper-trading-service-1','curl','-sS','--max-time','8','-w','\n%{http_code}','-H','X-Aiquant-Identity: '+token,'http://localhost:8083'+path],capture_output=True,text=True,timeout=12)
            raw,status=result.stdout.rsplit('\n',1)
            assert result.returncode==0 and status=='200'
            body=json.loads(raw);assert body['items']==[] and body['total']==0
        except Exception:raise RuntimeError('Read-only route verification failed for '+path) from None
        checks.append({'path':path,'status':200,'emptyRandomOwnerScope':True})
    print(json.dumps({'scope':'INTERNAL_HTTP_READ_ONLY_RANDOM_EMPTY_WORKSPACE_NO_USER_OR_DATA_CREATED','result':'PASSED','checks':checks}))
if __name__=='__main__':main()
