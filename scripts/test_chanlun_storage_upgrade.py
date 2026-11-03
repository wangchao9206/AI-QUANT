"""Rehearse V5 -> V7 using a schema-only-scope backup in a disposable DB.

The dump includes private research records, stays local, and is not committed.
All mutations and disabled task flags apply to the disposable clone only.
"""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import re
import subprocess
import time
import uuid


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--backup',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    prefix='aiquant-upgrade-verify-'+uuid.uuid4().hex[:10];db=prefix+'-db';java=prefix+'-java';created=[];report=None
    def docker(*parts,input=None):return subprocess.run(['docker',*parts],check=True,input=input,capture_output=True,text=True,encoding='utf-8').stdout.strip()
    def sql(statement):return docker('exec',db,'psql','-U','aiquant','-d','aiquant','-At','-v','ON_ERROR_STOP=1','-c',statement)
    def counts(tables):return {name:int(sql('select count(*) from chanlun.'+name)) for name in tables}
    try:
        docker('network','create','--internal',prefix)
        docker('run','-d','--name',db,'--network',prefix,'--network-alias','db','-e','POSTGRES_DB=aiquant','-e','POSTGRES_USER=aiquant','-e','POSTGRES_PASSWORD=isolated-fixture-only','postgres:17.6-alpine3.22');created.append(db)
        for _ in range(45):
            try:docker('exec',db,'pg_isready','-h','127.0.0.1','-U','aiquant','-d','aiquant');break
            except subprocess.CalledProcessError:time.sleep(1)
        subprocess.run(['docker','exec','-i',db,'pg_restore','-U','aiquant','-d','aiquant','--exit-on-error','--no-owner'],input=args.backup.read_bytes(),check=True,capture_output=True)
        before_version=int(sql("select max(version::int) from chanlun.flyway_schema_history where success and version is not null"));assert before_version==5,before_version
        tables=sql("select tablename from pg_tables where schemaname='chanlun' and tablename<>'flyway_schema_history' order by tablename").splitlines()
        assert all(re.fullmatch('[a-z_]+',name) for name in tables)
        before_counts=counts(tables)
        before_head=json.loads(sql("select coalesce(jsonb_object_agg(m.id::text,s.analysis),'{}'::jsonb) from chanlun.monitor m join chanlun.monitor_snapshot s on s.id=m.latest_snapshot_id"))
        # This is the isolated copy, never the running system.
        sql('update chanlun.monitor set enabled=false')
        docker('run','-d','--name',java,'--network',prefix,'-e','DATABASE_URL=jdbc:postgresql://db:5432/aiquant','-e','DATABASE_USERNAME=aiquant','-e','DATABASE_PASSWORD=isolated-fixture-only','ai-quant-chanlun-service');created.append(java)
        for _ in range(70):
            version=sql("select max(version::int) from chanlun.flyway_schema_history where success and version is not null")
            if version=='7':break
            time.sleep(1)
        else:raise RuntimeError('Migration did not reach V7')
        after_counts=counts(tables);assert before_counts==after_counts,(before_counts,after_counts)
        after_head=json.loads(sql("select coalesce(jsonb_object_agg(id::text,latest_analysis),'{}'::jsonb) from chanlun.monitor where latest_analysis is not null"))
        assert before_head==after_head
        assert int(sql('select count(*) from chanlun.monitor_event e left join chanlun.monitor_snapshot s on s.id=e.snapshot_id where s.id is null'))==0
        report={'status':'PASS','verifiedAt':datetime.now(timezone.utc).isoformat(),'scope':'ISOLATED_LOCAL_PRODUCTION_SCHEMA_BACKUP_REHEARSAL_NO_EXTERNAL_CONNECTIONS','fromVersion':before_version,'toVersion':7,'tableRowsPreserved':before_counts,'headsBackfilledUnchanged':len(before_head),'checks':['all_existing_table_row_counts_preserved','current_heads_equal_old_immutable_snapshot_content','all_event_snapshot_references_preserved'],'cleanupCompleted':False}
    except Exception:
        if java in created:
            logs=subprocess.run(['docker','logs','--tail','40',java],capture_output=True,text=True,encoding='utf-8');print(logs.stdout);print(logs.stderr)
        raise
    finally:
        for name in reversed(created):docker('rm','-f',name)
        docker('network','rm',prefix)
        if report:report['cleanupCompleted']=True
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
