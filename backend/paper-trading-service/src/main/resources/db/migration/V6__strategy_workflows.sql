create table strategy_workflow (
    id uuid primary key,
    client_request_id varchar(128) not null unique,
    name varchar(120) not null,
    description varchar(1000) not null default '',
    definition jsonb not null,
    revision integer not null default 1,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create table strategy_workflow_version (
    id uuid primary key,
    workflow_id uuid not null references strategy_workflow(id),
    version integer not null,
    command_id varchar(128) not null,
    source_revision integer not null,
    name varchar(120) not null,
    definition jsonb not null,
    engine_version varchar(64) not null,
    required_bars integer not null,
    lots integer not null check(lots between 1 and 1000000),
    stop_loss_atr numeric(10,4) not null check(stop_loss_atr between 0.1 and 20),
    take_profit_atr numeric(10,4) not null check(take_profit_atr between 0.1 and 50),
    created_at timestamptz not null default now(),
    unique(workflow_id,version),
    unique(workflow_id,command_id)
);
alter table paper_session drop constraint paper_strategy_id_check;
alter table paper_session add constraint paper_strategy_id_check check(strategy_id in
    ('MANUAL','HOLISTIC_14D','MOMENTUM_BREAKOUT','BOLLINGER_REVERSAL','DUAL_THRUST','ADAPTIVE_CTA','BUY_AND_HOLD','WORKFLOW'));
alter table paper_session add column workflow_version_id uuid references strategy_workflow_version(id),
    add column workflow_snapshot jsonb;
alter table paper_strategy_decision add column node_trace jsonb not null default '[]'::jsonb;
