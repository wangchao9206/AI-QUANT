-- Immutable research receipts and explicitly unverified local imports. No old data is moved.
alter table paper_trading.decision_case alter column source_event_id drop not null;
alter table paper_trading.decision_case add column source_kind varchar(24) not null default 'MONITOR_EVENT';
alter table paper_trading.decision_case add column source_key varchar(128);
alter table paper_trading.decision_case add constraint decision_source_kind check(source_kind in ('MONITOR_EVENT','SERVER_CALC','LOCAL_IMPORT'));
create unique index decision_case_source on paper_trading.decision_case(tenant_id,owner_id,source_kind,source_key) where source_key is not null;
create table paper_trading.decision_research_source (
 id uuid primary key,tenant_id uuid not null default nullif(current_setting('app.tenant_id',true),'')::uuid,
 owner_id uuid not null,kind varchar(24) not null check(kind in ('SERVER_CALC','LOCAL_IMPORT')),
 command_id uuid not null,input_hash varchar(64) not null,source_hash varchar(64) not null,
 plan_hash varchar(64) not null,request jsonb not null,snapshot jsonb not null,raw_payload text,
 created_at timestamptz not null default now(),unique(tenant_id,owner_id,id),unique(tenant_id,owner_id,command_id)
);
create unique index decision_local_content on paper_trading.decision_research_source(tenant_id,owner_id,source_hash) where kind='LOCAL_IMPORT';
create table paper_trading.decision_source_link (
 tenant_id uuid not null default nullif(current_setting('app.tenant_id',true),'')::uuid,
 owner_id uuid not null,case_id uuid not null,source_id uuid primary key,
 created_at timestamptz not null default now(),
 foreign key(tenant_id,owner_id,case_id) references paper_trading.decision_case(tenant_id,owner_id,id),
 foreign key(tenant_id,owner_id,source_id) references paper_trading.decision_research_source(tenant_id,owner_id,id)
);
do $$ declare t text; begin
 foreach t in array array['decision_research_source','decision_source_link'] loop
  execute format('alter table paper_trading.%I enable row level security',t);
  execute format('alter table paper_trading.%I force row level security',t);
  execute format('create policy private_owner on paper_trading.%I using(tenant_id=nullif(current_setting(''app.tenant_id'',true),'''')::uuid and owner_id=nullif(current_setting(''app.user_id'',true),'''')::uuid and current_setting(''app.research_read'',true)=''true'') with check(tenant_id=nullif(current_setting(''app.tenant_id'',true),'''')::uuid and owner_id=nullif(current_setting(''app.user_id'',true),'''')::uuid and current_setting(''app.research_read'',true)=''true'')',t);
  execute format('grant select,insert on paper_trading.%I to aiquant_tenant',t);
 end loop;
end $$;
create index decision_source_case on paper_trading.decision_source_link(tenant_id,owner_id,case_id,created_at desc);
