create table paper_trading.decision_monitor (
 tenant_id uuid not null default nullif(current_setting('app.tenant_id',true),'')::uuid,
 owner_id uuid not null,plan_id uuid not null,monitor_id uuid not null,snapshot jsonb not null,
 created_at timestamptz not null default now(),primary key(plan_id,monitor_id),
 foreign key(tenant_id,owner_id,plan_id) references paper_trading.decision_plan(tenant_id,owner_id,id)
);
alter table paper_trading.decision_monitor enable row level security;
alter table paper_trading.decision_monitor force row level security;
create policy private_owner on paper_trading.decision_monitor using(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid and owner_id=nullif(current_setting('app.user_id',true),'')::uuid) with check(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid and owner_id=nullif(current_setting('app.user_id',true),'')::uuid);
grant select,insert on paper_trading.decision_monitor to aiquant_tenant;
