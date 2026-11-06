-- Existing private records are retained in the default workspace.
-- Execute as the migration owner; request transactions SET LOCAL ROLE to this restricted role.
do $$
declare s text := current_schema(); r record; f record; child_cols text; parent_cols text;
begin
 perform pg_advisory_xact_lock(71203002);
 if not exists(select 1 from pg_roles where rolname='aiquant_tenant') then
   create role aiquant_tenant nologin nosuperuser nocreatedb nocreaterole noinherit nobypassrls;
 end if;
 execute format('grant aiquant_tenant to %I',current_user);
 execute format('grant usage on schema %I to aiquant_tenant',s);
 for r in select tablename from pg_tables where schemaname=s and tablename<>'flyway_schema_history' loop
   execute format('alter table %I.%I add column tenant_id uuid not null default %L::uuid',s,r.tablename,'00000000-0000-0000-0000-000000000001');
   execute format('alter table %I.%I alter column tenant_id set default nullif(current_setting(''app.tenant_id'',true),'''')::uuid',s,r.tablename);
   if s='paper_trading' and r.tablename='reading_book' then
     execute format('alter table %I.%I alter column tenant_id drop not null',s,r.tablename);
     execute format('update %I.%I set tenant_id=null where slug is not null',s,r.tablename);
   end if;
   execute format('create index on %I.%I(tenant_id)',s,r.tablename);
   execute format('alter table %I.%I enable row level security',s,r.tablename);
   execute format('alter table %I.%I force row level security',s,r.tablename);
   execute format('create policy tenant_private on %I.%I using (tenant_id=nullif(current_setting(''app.tenant_id'',true),'''')::uuid) with check (tenant_id=nullif(current_setting(''app.tenant_id'',true),'''')::uuid)',s,r.tablename);
   if s='paper_trading' and r.tablename='reading_book' then
     execute format('create policy public_books on %I.%I for select using (tenant_id is null and slug is not null)',s,r.tablename);
   end if;
   execute format('grant select,insert,update,delete on %I.%I to aiquant_tenant',s,r.tablename);
 end loop;
 execute format('grant usage,select on all sequences in schema %I to aiquant_tenant',s);
 -- UUIDs alone do not prevent a child from referencing another tenant's parent.
 for f in
   select c.oid,c.conrelid,c.confrelid,c.conkey,c.confkey,
     cn.nspname as child_schema,ct.relname as child_table,
     pn.nspname as parent_schema,pt.relname as parent_table
   from pg_constraint c join pg_class ct on ct.oid=c.conrelid join pg_namespace cn on cn.oid=ct.relnamespace
   join pg_class pt on pt.oid=c.confrelid join pg_namespace pn on pn.oid=pt.relnamespace
   where c.contype='f' and cn.nspname=s and pn.nspname=s
     and pt.relname<>'reading_book'
 loop
   select string_agg(format('%I',a.attname),',' order by k.ord) into child_cols
    from unnest(f.conkey) with ordinality k(num,ord) join pg_attribute a on a.attrelid=f.conrelid and a.attnum=k.num;
   select string_agg(format('%I',a.attname),',' order by k.ord) into parent_cols
    from unnest(f.confkey) with ordinality k(num,ord) join pg_attribute a on a.attrelid=f.confrelid and a.attnum=k.num;
   execute format('create unique index %I on %I.%I(tenant_id,%s)','tenant_parent_'||f.oid,f.parent_schema,f.parent_table,parent_cols);
   execute format('alter table %I.%I add constraint %I foreign key(tenant_id,%s) references %I.%I(tenant_id,%s)',f.child_schema,f.child_table,'tenant_link_'||f.oid,child_cols,f.parent_schema,f.parent_table,parent_cols);
 end loop;
end $$;
