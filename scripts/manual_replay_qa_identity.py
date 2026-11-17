"""Provision/clean an isolated QA tenant without touching the bootstrap administrator."""
import json,secrets,subprocess,sys,uuid
from pathlib import Path
import bcrypt
from compose import command,ROOT

STATE=ROOT/'.test-tmp/manual-replay-qa-identity.json'
env={}
for line in (ROOT/'infrastructure/.env').read_text(encoding='utf-8-sig').splitlines():
    if '=' in line and not line.lstrip().startswith('#'):
        k,v=line.split('=',1);env[k.strip()]=v.strip().strip('\"\'')

def sql(value):
    result=subprocess.run(command('light',['exec','-T','postgres','psql','-U',env.get('POSTGRES_USER','aiquant'),'-d',env.get('POSTGRES_DB','aiquant'),'-v','ON_ERROR_STOP=1']),input=value,encoding='utf-8',capture_output=True)
    if result.returncode:raise RuntimeError(result.stderr[-1800:])
    return result.stdout

if sys.argv[1]=='create':
    if STATE.exists():raise SystemExit('QA identity already provisioned; reuse or clean it first.')
    user=str(uuid.uuid4());tenant=str(uuid.uuid4());name='replay_qa_'+secrets.token_hex(5);password=secrets.token_urlsafe(24)
    hashed=bcrypt.hashpw(password.encode(),bcrypt.gensalt()).decode()
    sql(f"""begin;
      insert into identity.tenant(id,name) values('{tenant}','隔离分钟回放验收');
      insert into identity.account(id,username,password_hash,verified,must_change) values('{user}','{name}','{hashed}',true,false);
      insert into identity.membership(tenant_id,user_id,role) values('{tenant}','{user}','OWNER');commit;""")
    STATE.write_text(json.dumps(dict(userId=user,tenantId=tenant,username=name,password=password)),encoding='utf-8')
    print('Isolated QA identity provisioned; credentials kept only in ignored local QA state.')
elif sys.argv[1]=='clean':
    s=json.loads(STATE.read_text());user=str(uuid.UUID(s['userId']));tenant=str(uuid.UUID(s['tenantId']))
    sql(f"""begin;
      delete from paper_trading.paper_session where tenant_id='{tenant}';
      delete from identity.workspace_revision where tenant_id='{tenant}';
      delete from identity.workspace_document where tenant_id='{tenant}';
      delete from identity.session where user_id='{user}';
      delete from identity.challenge where user_id='{user}';
      delete from identity.api_key where user_id='{user}';
      delete from identity.external_identity where user_id='{user}';
      delete from identity.role_assignment where tenant_id='{tenant}';
      delete from identity.access_role where tenant_id='{tenant}';
      delete from identity.membership where user_id='{user}';
      delete from identity.account where id='{user}';
      delete from identity.tenant where id='{tenant}';commit;""")
    STATE.unlink();print('Only the isolated QA identity, tenant and replay records were removed; administrator unchanged.')
elif sys.argv[1]=='status':
    print(sql("select username,must_change,enabled from identity.account where username='admin';"))
elif sys.argv[1]=='strip-minute-fixture':
    s=json.loads(STATE.read_text());tenant=str(uuid.UUID(s['tenantId']))
    sql(f"update paper_trading.paper_session set replay_context=replay_context-'minuteBars'-'completeTradingDates' where tenant_id='{tenant}';")
    print('Only isolated QA sessions now emulate the preceding archive format.')
