create unique index workflow_version_tenant_identity on paper_trading.strategy_workflow_version(tenant_id,id);
create table paper_trading.workflow_shadow (
 id uuid primary key,
 tenant_id uuid not null default nullif(current_setting('app.tenant_id',true),'')::uuid,
 client_request_id uuid not null,
 workflow_version_id uuid not null,
 symbol varchar(16) not null,
 as_of timestamptz not null,
 direction int not null check(direction in (-1,0,1)),
 result jsonb not null,
 created_at timestamptz not null default now(),
 unique(tenant_id,id), unique(tenant_id,client_request_id),
 foreign key(tenant_id,workflow_version_id) references paper_trading.strategy_workflow_version(tenant_id,id)
);
create index workflow_shadow_version_recent on paper_trading.workflow_shadow(tenant_id,workflow_version_id,created_at desc);
alter table paper_trading.workflow_shadow enable row level security;
alter table paper_trading.workflow_shadow force row level security;
create policy tenant_private on paper_trading.workflow_shadow
 using(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid)
 with check(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid);
grant select,insert on paper_trading.workflow_shadow to aiquant_tenant;
