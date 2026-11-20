create table paper_automation_run (
    id uuid primary key,
    tenant_id uuid not null default nullif(current_setting('app.tenant_id',true),'')::uuid,
    session_id uuid not null,
    contract varchar(16) not null,
    owner_id uuid not null,
    strategy varchar(32) not null check(strategy in ('MA20_MACD','HOLISTIC_14D','MOMENTUM_BREAKOUT','BOLLINGER_REVERSAL','DUAL_THRUST','ADAPTIVE_CTA','BUY_AND_HOLD','WORKFLOW')),
    lots integer not null check(lots between 1 and 1000000),
    stop_loss_ticks integer not null default 10 check(stop_loss_ticks between 0 and 10000),
    stop_loss_atr numeric(10,4) not null default 0 check(stop_loss_atr between 0 and 20),
    take_profit_atr numeric(10,4) not null default 0 check(take_profit_atr between 0 and 50),
    intraday_only boolean not null default true,
    workflow_snapshot jsonb not null default '{}',
    enabled boolean not null default true,
    revision bigint not null default 1,
    status varchar(24) not null default 'STARTING',
    message varchar(1200) not null default '',
    last_signal_time timestamptz,
    entry_atr numeric(20,6),
    blocked_trading_date varchar(10),
    checked_at timestamptz,
    next_check_at timestamptz not null default now(),
    lease_owner uuid,
    lease_until timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique(tenant_id,id),
    foreign key(tenant_id,session_id,contract) references paper_portfolio_position(tenant_id,session_id,contract) on delete cascade
);
create unique index paper_automation_active_contract on paper_automation_run(tenant_id,session_id,contract) where enabled;
create index paper_automation_due on paper_automation_run(next_check_at) where enabled;
alter table paper_order add column automation_run_id uuid;
alter table paper_order add constraint paper_order_automation_run foreign key(tenant_id,automation_run_id) references paper_automation_run(tenant_id,id);
create table paper_automation_event (
    id uuid primary key,
    tenant_id uuid not null default nullif(current_setting('app.tenant_id',true),'')::uuid,
    run_id uuid not null,
    signal_time timestamptz not null,
    signal varchar(16) not null,
    status varchar(24) not null,
    reason varchar(1200) not null,
    evidence jsonb not null default '{}',
    created_at timestamptz not null default now(),
    unique(run_id,signal_time),
    foreign key(tenant_id,run_id) references paper_automation_run(tenant_id,id) on delete cascade
);
alter table paper_automation_run enable row level security;
alter table paper_automation_run force row level security;
alter table paper_automation_event enable row level security;
alter table paper_automation_event force row level security;
create policy tenant_private on paper_automation_run using(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid) with check(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid);
create policy tenant_private on paper_automation_event using(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid) with check(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid);
grant select,insert,update,delete on paper_automation_run,paper_automation_event to aiquant_tenant;
