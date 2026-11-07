-- Additive, private decision records. Existing sessions and journals are untouched.
create table paper_trading.decision_case (
 id uuid primary key, tenant_id uuid not null default nullif(current_setting('app.tenant_id',true),'')::uuid,
 owner_id uuid not null, symbol varchar(16) not null, source_event_id bigint not null,
 origin jsonb not null, version int not null default 0, created_at timestamptz not null default now(),
 updated_at timestamptz not null default now(), unique(tenant_id,owner_id,id), unique(tenant_id,owner_id,source_event_id)
);
create table paper_trading.decision_plan (
 id uuid primary key, tenant_id uuid not null default nullif(current_setting('app.tenant_id',true),'')::uuid,
 owner_id uuid not null, case_id uuid not null, version int not null check(version>0), command_id uuid not null,
 fields jsonb not null, created_at timestamptz not null default now(),
 unique(tenant_id,owner_id,id), unique(case_id,version), unique(tenant_id,owner_id,command_id),
 foreign key(tenant_id,owner_id,case_id) references paper_trading.decision_case(tenant_id,owner_id,id)
);
create table paper_trading.decision_review (
 id uuid primary key, tenant_id uuid not null default nullif(current_setting('app.tenant_id',true),'')::uuid,
 owner_id uuid not null, plan_id uuid not null, command_id uuid not null, outcome varchar(24) not null,
 notes varchar(4000) not null, created_at timestamptz not null default now(),
 unique(tenant_id,owner_id,command_id),
 foreign key(tenant_id,owner_id,plan_id) references paper_trading.decision_plan(tenant_id,owner_id,id)
);
create unique index decision_session_identity on paper_trading.paper_session(tenant_id,id);
create table paper_trading.decision_paper (
 tenant_id uuid not null default nullif(current_setting('app.tenant_id',true),'')::uuid,
 owner_id uuid not null, plan_id uuid primary key, session_id uuid not null, command_id uuid not null,
 readiness jsonb not null, created_at timestamptz not null default now(), unique(tenant_id,owner_id,command_id),
 foreign key(tenant_id,owner_id,plan_id) references paper_trading.decision_plan(tenant_id,owner_id,id),
 foreign key(tenant_id,session_id) references paper_trading.paper_session(tenant_id,id)
);
do $$ declare t text; begin
 foreach t in array array['decision_case','decision_plan','decision_review','decision_paper'] loop
  execute format('alter table paper_trading.%I enable row level security',t);
  execute format('alter table paper_trading.%I force row level security',t);
  execute format('create policy private_owner on paper_trading.%I using(tenant_id=nullif(current_setting(''app.tenant_id'',true),'''')::uuid and owner_id=nullif(current_setting(''app.user_id'',true),'''')::uuid) with check(tenant_id=nullif(current_setting(''app.tenant_id'',true),'''')::uuid and owner_id=nullif(current_setting(''app.user_id'',true),'''')::uuid)',t);
  execute format('grant select,insert on paper_trading.%I to aiquant_tenant',t);
 end loop;
end $$;
grant update(version,updated_at) on paper_trading.decision_case to aiquant_tenant;
create index decision_case_recent on paper_trading.decision_case(tenant_id,owner_id,updated_at desc);
