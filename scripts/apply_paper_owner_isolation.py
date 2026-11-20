"""Apply the reviewed, idempotent owner policy before the full image rollout."""
import json
import subprocess
from pathlib import Path
from compose import command, ROOT


def main():
    config={}
    for line in (ROOT/'infrastructure/.env').read_text(encoding='utf-8-sig').splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            k,v=line.split('=',1);config[k.strip()]=v.strip().strip('\"\'')
    user,database=config.get('POSTGRES_USER','aiquant'),config.get('POSTGRES_DB','aiquant')
    migration=(ROOT/'backend/paper-trading-service/src/main/resources/db/migration/V18__private_paper_accounts.sql').read_text(encoding='utf-8')
    tables=['paper_session','paper_order','paper_fill','paper_position','paper_portfolio_position','paper_fill_note',
            'paper_automation_run','paper_automation_event','personal_training','personal_training_event','personal_reflection','personal_strategy_version']
    fingerprint="""select jsonb_build_object(
      'sessions',(select coalesce(jsonb_agg(jsonb_build_array(id,cash_balance,equity,realized_pnl,commission_paid) order by id),'[]'::jsonb) from paper_session),
      'fills',(select coalesce(jsonb_agg(id order by id),'[]'::jsonb) from paper_fill),
      'orders',(select coalesce(jsonb_agg(id order by id),'[]'::jsonb) from paper_order),
      'notes',(select count(*) from paper_fill_note),
      'positions',(select count(*) from paper_position)+(select count(*) from paper_portfolio_position)) as value"""
    sql="begin; set local lock_timeout='10s'; set local search_path=paper_trading;\n"
    sql+='lock table '+','.join('paper_trading.'+t for t in tables)+' in access exclusive mode;\n'
    sql+='create temporary table owner_fix_before on commit drop as '+fingerprint+';\n'
    sql+=migration+'\n'
    sql+="do $$ begin if (select value from owner_fix_before) is distinct from ("+fingerprint+") then raise exception 'Original ledger changed'; end if; end $$;\ncommit;\n"
    sql+="select json_build_object('status','PASS','originalLedgerPreserved',true,'owned',(select count(*) from paper_trading.paper_session where owner_id is not null),'unassigned',(select count(*) from paper_trading.paper_session where owner_id is null))::text;"
    result=subprocess.run(command('light',['exec','-T','postgres','psql','-U',user,'-d',database,'-At','-v','ON_ERROR_STOP=1']),
                          input=sql,encoding='utf-8',capture_output=True)
    if result.returncode:raise RuntimeError(result.stderr[-2200:])
    line=next(line for line in reversed(result.stdout.splitlines()) if line.startswith('{'))
    receipt=json.loads(line)
    target=ROOT/'.test-tmp/paper-owner-isolation';target.mkdir(parents=True,exist_ok=True)
    (target/'migration.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    print(json.dumps(receipt))


if __name__=='__main__':main()
