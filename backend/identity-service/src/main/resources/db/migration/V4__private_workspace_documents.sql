-- Private UI state only. Existing accounts, permissions and business ledgers are untouched.
do $$ begin
 if not exists(select 1 from pg_roles where rolname='aiquant_workspace') then
  create role aiquant_workspace nologin nosuperuser nocreatedb nocreaterole noinherit nobypassrls;
 end if;
 execute format('grant aiquant_workspace to %I',current_user);
end $$;
create table identity.workspace_document (
 tenant_id uuid not null references identity.tenant(id), owner_id uuid not null references identity.account(id),
 kind varchar(16) not null check(kind in ('PREFERENCES','CHART')), document_key varchar(100) not null,
 revision bigint not null check(revision>0), content jsonb not null check(octet_length(content::text)<=65536),
 updated_at timestamptz not null default now(), primary key(tenant_id,owner_id,kind,document_key)
);
create table identity.workspace_revision (
 tenant_id uuid not null, owner_id uuid not null, kind varchar(16) not null, document_key varchar(100) not null,
 command_id uuid not null, base_revision bigint not null check(base_revision>=0), revision bigint not null check(revision>0),
 content jsonb not null check(octet_length(content::text)<=65536), created_at timestamptz not null default now(),
 primary key(tenant_id,owner_id,command_id), unique(tenant_id,owner_id,kind,document_key,revision),
 foreign key(tenant_id,owner_id,kind,document_key) references identity.workspace_document(tenant_id,owner_id,kind,document_key)
);
grant usage on schema identity to aiquant_workspace;
grant select,insert on identity.workspace_document,identity.workspace_revision to aiquant_workspace;
grant update(revision,content,updated_at) on identity.workspace_document to aiquant_workspace;
do $$ declare t text; begin
 foreach t in array array['workspace_document','workspace_revision'] loop
  execute format('alter table identity.%I enable row level security',t);
  execute format('alter table identity.%I force row level security',t);
  execute format('create policy private_workspace_owner on identity.%I using(tenant_id=nullif(current_setting(''app.workspace_tenant'',true),'''')::uuid and owner_id=nullif(current_setting(''app.workspace_owner'',true),'''')::uuid) with check(tenant_id=nullif(current_setting(''app.workspace_tenant'',true),'''')::uuid and owner_id=nullif(current_setting(''app.workspace_owner'',true),'''')::uuid)',t);
 end loop;
end $$;
