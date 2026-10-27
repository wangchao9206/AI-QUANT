alter table paper_session
    add column strategy_id varchar(32) not null default 'MANUAL',
    add column strategy_lots integer not null default 1 check (strategy_lots between 1 and 1000000),
    add column stop_loss_atr numeric(10,4) not null default 2 check (stop_loss_atr > 0),
    add column take_profit_atr numeric(10,4) not null default 3 check (take_profit_atr > 0),
    add column market_state varchar(24) not null default 'UNKNOWN',
    add column execution_message varchar(500) not null default '',
    add column peak_equity numeric(20,2) not null default 0,
    add column max_drawdown_pct numeric(12,6) not null default 0;
alter table paper_session add constraint paper_strategy_id_check check (strategy_id in
    ('MANUAL','HOLISTIC_14D','MOMENTUM_BREAKOUT','BOLLINGER_REVERSAL','DUAL_THRUST','ADAPTIVE_CTA','BUY_AND_HOLD'));
update paper_session set peak_equity = greatest(initial_cash, equity);

alter table paper_order
    add column origin varchar(16) not null default 'MANUAL',
    add column reason varchar(240) not null default '手动模拟委托',
    add column risk_atr numeric(20,6);
alter table paper_position add column risk_atr numeric(20,6);

create table paper_signal_bar (
    session_id uuid not null references paper_session(id) on delete cascade,
    kind varchar(16) not null check (kind in ('SIGNAL','EXECUTION')),
    market_time timestamptz not null,
    open_price numeric(20,6) not null, high_price numeric(20,6) not null,
    low_price numeric(20,6) not null, close_price numeric(20,6) not null,
    volume bigint not null, open_interest bigint not null,
    primary key (session_id,kind,market_time)
);

create table paper_strategy_decision (
    id bigint generated always as identity primary key,
    session_id uuid not null references paper_session(id) on delete cascade,
    signal_time timestamptz not null,
    signal varchar(16) not null,
    reason varchar(240) not null,
    model_version varchar(80) not null,
    history_count integer not null,
    created_at timestamptz not null default now(),
    unique (session_id,signal_time)
);
