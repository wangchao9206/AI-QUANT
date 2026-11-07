create table paper_trading.decision_alert_subscription (
 tenant_id uuid not null default nullif(current_setting('app.tenant_id',true),'')::uuid,
 owner_id uuid not null,plan_id uuid primary key,revision bigint not null default 1,
 enabled boolean not null,entry_mode varchar(16) not null check(entry_mode in ('BREAKOUT','PULLBACK')),
 status varchar(24) not null,message text not null default '',state jsonb not null default '{}',
 checked_at timestamptz,next_check_at timestamptz not null default now(),lease_owner uuid,lease_until timestamptz,
 created_at timestamptz not null default now(),updated_at timestamptz not null default now(),
 unique(tenant_id,owner_id,plan_id),
 foreign key(tenant_id,owner_id,plan_id) references paper_trading.decision_plan(tenant_id,owner_id,id)
);
create index decision_alert_due on paper_trading.decision_alert_subscription(next_check_at) where enabled;
create table paper_trading.decision_alert_event (
 id uuid primary key,tenant_id uuid not null default nullif(current_setting('app.tenant_id',true),'')::uuid,
 owner_id uuid not null,plan_id uuid not null,kind varchar(16) not null check(kind in ('ENTRY','STOP','TARGET','EXPIRED')),
 observed_at timestamptz not null,evidence jsonb not null,created_at timestamptz not null default now(),acknowledged_at timestamptz,
 unique(plan_id,kind),foreign key(tenant_id,owner_id,plan_id) references paper_trading.decision_alert_subscription(tenant_id,owner_id,plan_id)
);
create index decision_alert_recent on paper_trading.decision_alert_event(tenant_id,owner_id,created_at desc,id);
do $$ declare t text; begin
 foreach t in array array['decision_alert_subscription','decision_alert_event'] loop
  execute format('alter table paper_trading.%I enable row level security',t);
  execute format('alter table paper_trading.%I force row level security',t);
  execute format('create policy private_owner on paper_trading.%I using(tenant_id=nullif(current_setting(''app.tenant_id'',true),'''')::uuid and owner_id=nullif(current_setting(''app.user_id'',true),'''')::uuid) with check(tenant_id=nullif(current_setting(''app.tenant_id'',true),'''')::uuid and owner_id=nullif(current_setting(''app.user_id'',true),'''')::uuid)',t);
  execute format('grant select,insert on paper_trading.%I to aiquant_tenant',t);
 end loop;
end $$;
grant update(revision,enabled,status,message,state,checked_at,next_check_at,lease_owner,lease_until,updated_at) on paper_trading.decision_alert_subscription to aiquant_tenant;
grant update(acknowledged_at) on paper_trading.decision_alert_event to aiquant_tenant;
