"""Bounded, verified CSV archives for operational data; pruning is explicit.

Uses the existing PostgreSQL container's psql, never prints credentials or rows.
Business evidence, accounts, ledgers and monitor events are outside the allowlist.
"""
import argparse
import csv
from datetime import datetime,timedelta,timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import uuid

ROOT=Path(__file__).resolve().parents[1]
POLICIES={
    'quotes':('market.market_quote_snapshot',30,7,'symbol'),
    'terms':('market.market_term_snapshot',90,7,'contract_symbol'),
    'operations':('identity.operation_log',90,30,None),
    'audit':('identity.audit',365,90,None),
}


class Postgres:
    def __init__(self,container='ai-quant-postgres-1'):
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*',container):raise ValueError('Invalid PostgreSQL container name')
        self.container=container
    def args(self):
        return ['docker','exec','-i',self.container,'sh','-c',
                'exec psql -X -qAt -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"']
    def sql(self,sql):
        p=subprocess.run(self.args(),input=sql,text=True,encoding='utf-8',capture_output=True)
        if p.returncode:raise RuntimeError('PostgreSQL operation failed; no row contents are logged')
        return p.stdout.strip()
    def copy(self,source,destination):
        subprocess.run(['docker','cp',str(source),str(destination)],check=True,capture_output=True)
    def remove_temp(self,name):
        assert re.fullmatch(r'/tmp/aq-retention-[a-f0-9]{32}\.csv',name)
        subprocess.run(['docker','exec',self.container,'rm','-f','--',name],check=True,capture_output=True)


class Transaction:
    def __init__(self,pg):self.pg=pg;self.process=None
    def __enter__(self):
        self.process=subprocess.Popen(self.pg.args(),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                                      text=True,encoding='utf-8',bufsize=1)
        try:
            self.run("BEGIN ISOLATION LEVEL REPEATABLE READ; SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='120s'; SET LOCAL idle_in_transaction_session_timeout='120s';")
        except BaseException:
            self.__exit__()
            raise
        return self
    def run(self,sql):
        marker='done_'+uuid.uuid4().hex
        self.process.stdin.write(sql+'\n\\echo '+marker+'\n');self.process.stdin.flush()
        rows=[]
        while True:
            line=self.process.stdout.readline()
            if not line:raise RuntimeError('Archive transaction ended unexpectedly; inspect manifest and database before retrying')
            if line.strip()==marker:return rows
            if line.strip():rows.append(line.strip())
    def __exit__(self,*error):
        try:
            if self.process.poll() is None:self.run('ROLLBACK;')
        except (RuntimeError,BrokenPipeError):pass
        finally:
            try:self.process.stdin.close()
            except BrokenPipeError:pass
            try:self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait()
            self.process.stdout.close()


def metadata(tx,table):
    schema,name=table.split('.')
    query=f"""select json_agg(json_build_object('name',column_name,'type',udt_name,'nullable',is_nullable,
        'length',character_maximum_length,'precision',numeric_precision,'scale',numeric_scale,'identity',is_identity) order by ordinal_position)
        from information_schema.columns where table_schema='{schema}' and table_name='{name}';"""
    value=tx.run(query)[-1] if isinstance(tx,Transaction) else tx.sql(query)
    fields=json.loads(value)
    if not fields or any(f['name']=='tenant_id' for f in fields) and table.startswith('market.'):
        raise ValueError('Unsupported table layout')
    return fields


def cutoff_policy(key,days=None,now=None):
    table,default,minimum,latest=POLICIES[key]
    days=default if days is None else days
    if not minimum<=days<=36500:raise ValueError(f'{key}: retention must be between {minimum} and 36500 days')
    cutoff=(now or datetime.now(timezone.utc))-timedelta(days=days)
    condition=f"t.created_at < '{cutoff.isoformat()}'::timestamptz"
    if latest:condition+=f' and exists(select 1 from {table} n where n.{latest}=t.{latest} and n.observed_at>t.observed_at)'
    return table,days,cutoff,condition


def plan(pg,key,days=None):
    table,days,cutoff,condition=cutoff_policy(key,days)
    count=int(pg.sql(f'select count(*) from {table} t where {condition};'))
    return {'policy':key,'table':table,'retentionDays':days,'cutoff':cutoff.isoformat(),'eligibleRows':count,'action':'PLAN_ONLY'}


def secure_directory(folder):
    folder=folder.resolve()
    if folder==ROOT or ROOT in folder.parents:raise ValueError('Private archives must be outside the Git workspace')
    marker=folder/'.aiquant-retention'
    if folder.exists() and not marker.exists() and any(folder.iterdir()):raise ValueError('Use an empty dedicated archive directory')
    folder.mkdir(parents=True,exist_ok=True)
    if os.name=='nt':
        owner=subprocess.check_output(['whoami'],text=True).strip()
        subprocess.run(['icacls',str(folder),'/inheritance:r','/grant:r',f'{owner}:(OI)(CI)F','SYSTEM:(OI)(CI)F'],check=True,capture_output=True)
    else:folder.chmod(0o700)
    marker.touch(exist_ok=True)
    return folder


def write_manifest(path,value):
    temp=path.with_suffix('.pending')
    with temp.open('w',encoding='utf-8') as output:
        json.dump(value,output,ensure_ascii=False,indent=2);output.write('\n');output.flush();os.fsync(output.fileno())
    temp.replace(path)


def verify_archive(file,manifest):
    if hashlib.sha256(file.read_bytes()).hexdigest()!=manifest['compressedSha256']:raise ValueError('Compressed archive checksum mismatch')
    digest=hashlib.sha256()
    with gzip.open(file,'rb') as source:
        while chunk:=source.read(1024*1024):digest.update(chunk)
    if digest.hexdigest()!=manifest['csvSha256']:raise ValueError('CSV checksum mismatch')
    with gzip.open(file,'rt',encoding='utf-8',newline='') as source:
        rows=csv.reader(source);header=next(rows)
        if header!=[f['name'] for f in manifest['fields']]:raise ValueError('Archive columns do not match manifest')
        if sum(1 for _ in rows)!=manifest['rows']:raise ValueError('Archive row count mismatch')


def archive(pg,key,directory,days=None,batch=1000,prune=False):
    if not 1<=batch<=5000:raise ValueError('Batch must be between 1 and 5000')
    table,days,cutoff,condition=cutoff_policy(key,days)
    name=uuid.uuid4().hex;remote='/tmp/aq-retention-'+name+'.csv';raw=None
    try:
        with Transaction(pg) as tx:
            tx.run("do $$ begin if not pg_try_advisory_xact_lock(71203091) then raise exception 'Retention already running'; end if; end $$;")
            tx.run(f'lock table {table} in row exclusive mode;')
            if prune and int(tx.run(f"select count(*) from pg_constraint where contype='f' and confrelid='{table}'::regclass;")[-1]):
                raise ValueError('Referenced tables cannot be pruned by operational retention')
            # Lock the selected source rows before copying the same MVCC snapshot.
            tx.run(f'select t.id from {table} t where {condition} order by t.id limit {batch} for update;')
            tx.run(f'create temp table retention_batch on commit drop as select t.* from {table} t where {condition} order by t.id limit {batch};')
            count=int(tx.run('select count(*) from retention_batch;')[-1])
            if not count:return {'policy':key,'rows':0,'status':'NOTHING_DUE'}
            fields=metadata(tx,table)
            tx.run(f"\\copy retention_batch to '{remote}' with (format csv,header true,encoding 'UTF8')")
            folder=secure_directory(Path(directory));raw=folder/(name+'.csv')
            pg.copy(pg.container+':'+remote,raw)
            final=folder/(key+'-'+name+'.csv.gz');pending=final.with_suffix('.partial')
            with raw.open('rb') as source,gzip.open(pending,'wb') as output:shutil.copyfileobj(source,output)
            # Windows FlushFileBuffers requires a writable descriptor.
            with pending.open('r+b') as output:os.fsync(output.fileno())
            pending.replace(final)
            manifest={'format':'aiquant-retention-v1','policy':key,'table':table,'rows':count,'fields':fields,
                      'retentionDays':days,'cutoff':cutoff.isoformat(),'recordedAt':datetime.now(timezone.utc).isoformat(),
                      'archive':final.name,'csvSha256':hashlib.sha256(raw.read_bytes()).hexdigest(),
                      'compressedSha256':hashlib.sha256(final.read_bytes()).hexdigest(),'status':'PREPARED'}
            file=final.with_suffix('.json');write_manifest(file,manifest)
            verify_archive(final,manifest)
            if prune:
                removed=int(tx.run(f'with removed as (delete from {table} t using retention_batch b where t.id=b.id returning t.id) select count(*) from removed;')[-1])
                if removed!=count:raise RuntimeError('Deletion count mismatch; transaction will roll back')
            tx.run('COMMIT;')
            manifest['status']='PRUNED' if prune else 'ARCHIVED_SOURCE_RETAINED';write_manifest(file,manifest)
            return {'policy':key,'rows':count,'status':manifest['status'],'manifest':str(file)}
    finally:
        if raw and raw.exists():raw.unlink()
        pg.remove_temp(remote)


def restore(pg,manifest_path):
    manifest_path=Path(manifest_path).resolve()
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    key=manifest['policy']
    if manifest.get('format')!='aiquant-retention-v1' or key not in POLICIES or manifest.get('table')!=POLICIES[key][0]:raise ValueError('Unsupported archive manifest')
    file=(manifest_path.parent/manifest['archive']).resolve()
    if file.parent!=manifest_path.parent:raise ValueError('Archive must be adjacent to its manifest')
    verify_archive(file,manifest)
    secure_directory(manifest_path.parent)
    remote='/tmp/aq-retention-'+uuid.uuid4().hex+'.csv';raw=manifest_path.parent/(uuid.uuid4().hex+'.csv')
    table=manifest['table']
    try:
        with gzip.open(file,'rb') as source,raw.open('wb') as target:shutil.copyfileobj(source,target)
        pg.copy(raw,pg.container+':'+remote)
        with Transaction(pg) as tx:
            tx.run(f'lock table {table} in share row exclusive mode;')
            if metadata(tx,table)!=manifest['fields']:raise ValueError('Database layout changed; an explicit archive migration is required')
            tx.run(f'create temp table retention_restore (like {table} including defaults) on commit drop;')
            tx.run(f"\\copy retention_restore from '{remote}' with (format csv,header true,encoding 'UTF8')")
            differences=int(tx.run(f'select count(*) from {table} t join retention_restore r using(id) where to_jsonb(t)<>to_jsonb(r);')[-1])
            if differences:raise ValueError('Existing rows differ; restore will not overwrite them')
            tx.run(f'insert into {table} overriding system value select * from retention_restore on conflict(id) do nothing;')
            # Restore is a maintenance action; the table lock prevents INSERT/sequence races.
            tx.run(f"select setval(pg_get_serial_sequence('{table}','id'),greatest(coalesce((select max(id) from {table}),1),coalesce(pg_sequence_last_value(pg_get_serial_sequence('{table}','id')::regclass),1)),true);")
            tx.run('COMMIT;')
        return {'policy':key,'status':'RESTORED','rowsVerified':manifest['rows']}
    finally:
        if raw.exists():raw.unlink()
        pg.remove_temp(remote)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('plan','archive','restore'))
    parser.add_argument('--policy',choices=tuple(POLICIES))
    parser.add_argument('--container',default='ai-quant-postgres-1')
    parser.add_argument('--days',type=int)
    parser.add_argument('--batch',type=int,default=1000)
    parser.add_argument('--prune',action='store_true')
    parser.add_argument('--directory',type=Path,default=ROOT.parent/'ai-quant-archives')
    parser.add_argument('--manifest',type=Path)
    args=parser.parse_args();pg=Postgres(args.container)
    if args.action=='restore':
        if not args.manifest:parser.error('restore needs --manifest')
        result=restore(pg,args.manifest)
    elif args.action=='archive':
        if not args.policy:parser.error('archive needs --policy')
        result=archive(pg,args.policy,args.directory,args.days,args.batch,args.prune)
    else:result=[plan(pg,key,args.days) for key in ([args.policy] if args.policy else POLICIES)]
    print(json.dumps(result,ensure_ascii=True,indent=2))


if __name__=='__main__':main()
