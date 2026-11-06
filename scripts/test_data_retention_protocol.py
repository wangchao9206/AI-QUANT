"""Real PostgreSQL archive/prune/restore drill in an isolated temporary container."""
import json
from pathlib import Path
import subprocess
import tempfile
import time
import uuid
from unittest.mock import patch

from data_retention import Postgres,archive,plan,restore

ROOT=Path(__file__).resolve().parents[1]
NAME='aq-retention-check-'+uuid.uuid4().hex[:10]


def expect_error(call,kind=ValueError):
    try:call()
    except kind:return
    raise AssertionError('Expected archive protection to reject the operation')


try:
    subprocess.run(['docker','run','-d','--name',NAME,'--network','none','--memory','512m','--tmpfs','/var/lib/postgresql/data:rw,size=256m',
                    '-e','POSTGRES_DB=retention_test','-e','POSTGRES_USER=retention_test','-e','POSTGRES_PASSWORD=isolated-test-only','postgres:17.6-alpine3.22'],check=True,capture_output=True)
    for attempt in range(60):
        # The initdb bootstrap server exposes only a Unix socket; wait for final TCP readiness.
        if subprocess.run(['docker','exec',NAME,'pg_isready','-h','127.0.0.1','-U','retention_test','-d','retention_test'],capture_output=True).returncode==0:break
        time.sleep(1)
    else:raise AssertionError('Test PostgreSQL did not start')
    pg=Postgres(NAME)
    pg.sql('create schema market; set search_path=market;'+(ROOT/'backend/market-service/src/main/resources/db/migration/V1__market_schema.sql').read_text(encoding='utf-8'))
    pg.sql('create schema identity; set search_path=identity;'+(ROOT/'backend/identity-service/src/main/resources/db/migration/V1__identity.sql').read_text(encoding='utf-8'))
    pg.sql('set search_path=identity;'+(ROOT/'backend/identity-service/src/main/resources/db/migration/V2__administration.sql').read_text(encoding='utf-8'))
    pg.sql("""insert into market.market_quote_snapshot(symbol,display_name,price,price_change,change_pct,source,observed_at,created_at) values
      ('FUM','燃油',100,0,0,'TEST',now()-interval '100 days',now()-interval '100 days'),
      ('FUM','燃油',101,0,0,'TEST',now()-interval '70 days',now()-interval '70 days'),
      ('RBM','螺纹',102,0,0,'TEST',now()-interval '100 days',now()-interval '100 days'),
      ('FUM','燃油',103,0,0,'TEST',now(),now());
      insert into identity.audit(action,target,created_at) values('TEST',E'中文\\n"quoted"',now()-interval '400 days'),
        ('TEST',null,now()-interval '400 days'),('TEST','',now()-interval '400 days'),('TEST',null,now());
      update identity.audit set before_state=jsonb_build_object('nested',jsonb_build_array(1,'值'::text,null)),
        after_state=jsonb_build_object('ok',true) where id=1;
      insert into market.market_term_snapshot(root_symbol,contract_symbol,maturity_date,price,observed_at,created_at) values
        ('FU','fu2701',current_date+30,100,now()-interval '100 days',now()-interval '100 days'),
        ('FU','fu2701',current_date+30,101,now()-interval '95 days',now()-interval '95 days');
      insert into identity.operation_log(method,path,status,duration_ms,created_at) values
        ('GET','/test',200,5,now()-interval '100 days'),('GET','/current',401,7,now());""")
    original=pg.sql('select row_to_json(t) from market.market_quote_snapshot t where id=1;')
    audit_original=pg.sql('select json_agg(t order by id) from identity.audit t;')
    assert plan(pg,'quotes')['eligibleRows']==2
    with tempfile.TemporaryDirectory(prefix='aiquant-retention-') as temp:
        folder=Path(temp)/'private'
        retained=archive(pg,'quotes',folder,batch=1)
        assert retained['status']=='ARCHIVED_SOURCE_RETAINED'
        assert pg.sql('select count(*) from market.market_quote_snapshot')=='4'
        import data_retention
        real_verify=data_retention.verify_archive
        with patch('data_retention.verify_archive',side_effect=ValueError('injected checksum failure')):
            expect_error(lambda:archive(pg,'quotes',folder,batch=1,prune=True))
        assert pg.sql('select count(*) from market.market_quote_snapshot')=='4'
        def concurrent(file,manifest):
            real_verify(file,manifest)
            pg.sql("insert into market.market_quote_snapshot(symbol,display_name,price,price_change,change_pct,source,observed_at,created_at) values('FUM','并发写入',104,0,0,'TEST',now()-interval '60 days',now()-interval '60 days');")
        with patch('data_retention.verify_archive',side_effect=concurrent):result=archive(pg,'quotes',folder,batch=1,prune=True)
        assert result['status']=='PRUNED' and result['rows']==1
        assert pg.sql('select count(*) from market.market_quote_snapshot where id=1')=='0'
        assert pg.sql('select count(*) from market.market_quote_snapshot where id=5')=='1'
        restore(pg,result['manifest']);restore(pg,result['manifest'])
        assert pg.sql('select row_to_json(t) from market.market_quote_snapshot t where id=1;')==original
        assert pg.sql('select count(*) from market.market_quote_snapshot')=='5'
        assert pg.sql('select count(*) from market.market_quote_snapshot where id=3')=='1'
        pg.sql('update market.market_quote_snapshot set price=999 where id=1;')
        expect_error(lambda:restore(pg,result['manifest']))
        assert pg.sql('select price::int from market.market_quote_snapshot where id=1')=='999'
        pg.sql('update market.market_quote_snapshot set price=100 where id=1;')
        pg.sql("select setval(pg_get_serial_sequence('market.market_quote_snapshot','id'),1000,true);")
        restore(pg,result['manifest'])
        assert pg.sql("select nextval(pg_get_serial_sequence('market.market_quote_snapshot','id'));")=='1001'
        audit=archive(pg,'audit',folder,prune=True)
        assert pg.sql('select count(*) from identity.audit')=='1'
        restore(pg,audit['manifest'])
        assert pg.sql('select json_agg(t order by id) from identity.audit t;')==audit_original
        assert pg.sql("select count(*) from identity.audit where target=E'中文\\n\"quoted\"'")=='1'
        for policy,table in [('terms','market.market_term_snapshot'),('operations','identity.operation_log')]:
            original_rows=pg.sql(f'select json_agg(t order by id) from {table} t;')
            assert plan(pg,policy)['eligibleRows']==1
            extra=archive(pg,policy,folder,prune=True)
            assert extra['rows']==1 and pg.sql(f'select count(*) from {table}')=='1'
            restore(pg,extra['manifest'])
            assert pg.sql(f'select json_agg(t order by id) from {table} t;')==original_rows
        manifest=Path(audit['manifest']);meta=json.loads(manifest.read_text(encoding='utf-8'))
        data=manifest.parent/meta['archive'];saved=data.read_bytes();data.write_bytes(saved+b'corrupt')
        expect_error(lambda:restore(pg,manifest));data.write_bytes(saved)
        pg.sql('alter table identity.audit add column future_field text;')
        expect_error(lambda:restore(pg,manifest))
        pg.sql('create table market.referenced(id bigint references market.market_quote_snapshot(id));')
        expect_error(lambda:archive(pg,'quotes',folder,prune=True))
        assert pg.sql('select count(*) from market.market_quote_snapshot')=='5'
    report={'status':'PASSED','isolatedDatabase':True,'checks':['latest snapshot preserved','bounded archive retains source by default',
        'checksum failure rolls back','prune deletes only locked archived IDs','concurrent new row retained','idempotent lossless restore',
        'conflicting existing row rejected','sequence never rewound','Unicode/newlines/null/empty/JSON CSV round trip',
        'term latest snapshot preserved','operation logs losslessly restored',
        'corrupted archive rejected','schema drift rejected','referenced table pruning rejected']}
    (ROOT/'.test-tmp').mkdir(exist_ok=True)
    (ROOT/'.test-tmp/round2-retention-protocol.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))
finally:
    subprocess.run(['docker','rm','-f',NAME],capture_output=True)
