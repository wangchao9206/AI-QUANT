create table paper_session (
    id uuid primary key,
    name varchar(80) not null,
    mode varchar(16) not null check (mode in ('LIVE', 'HISTORICAL')),
    symbol varchar(12) not null,
    status varchar(16) not null check (status in ('ACTIVE', 'PAUSED', 'COMPLETED', 'ERROR')),
    data_source varchar(120) not null,
    data_timestamp timestamptz not null,
    initial_cash numeric(20, 2) not null check (initial_cash > 0),
    cash_balance numeric(20, 2) not null,
    equity numeric(20, 2) not null,
    realized_pnl numeric(20, 2) not null default 0,
    commission_paid numeric(20, 2) not null default 0 check (commission_paid >= 0),
    slippage_paid numeric(20, 2) not null default 0 check (slippage_paid >= 0),
    margin_rate numeric(10, 6) not null check (margin_rate > 0 and margin_rate <= 1),
    fee_rate numeric(10, 8) not null check (fee_rate >= 0 and fee_rate <= 0.02),
    slippage_ticks numeric(10, 4) not null check (slippage_ticks >= 0 and slippage_ticks <= 100),
    max_participation_rate numeric(10, 6) not null check (max_participation_rate > 0 and max_participation_rate <= 1),
    auto_roll boolean not null default true,
    current_bar_index integer not null default 0 check (current_bar_index >= 0),
    total_bars integer not null default 0 check (total_bars >= 0),
    current_market_time timestamptz not null,
    current_contract varchar(16) not null,
    current_price numeric(20, 6) not null check (current_price > 0),
    volume_multiple integer not null check (volume_multiple > 0),
    price_tick numeric(20, 6) not null check (price_tick > 0),
    margin_per_lot numeric(20, 2) not null check (margin_per_lot > 0),
    commission_per_lot numeric(20, 6) not null check (commission_per_lot >= 0),
    version bigint not null default 0,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index paper_session_updated_idx on paper_session (updated_at desc);

create table paper_scenario_bar (
    id bigint generated always as identity primary key,
    session_id uuid not null references paper_session(id) on delete cascade,
    bar_index integer not null check (bar_index >= 0),
    market_time timestamptz not null,
    contract varchar(16) not null,
    open_price numeric(20, 6) not null check (open_price > 0),
    high_price numeric(20, 6) not null check (high_price >= open_price),
    low_price numeric(20, 6) not null check (low_price <= open_price),
    close_price numeric(20, 6) not null check (close_price > 0),
    volume bigint not null check (volume >= 0),
    open_interest bigint not null check (open_interest >= 0),
    unique (session_id, bar_index)
);

create index paper_scenario_bar_session_time_idx on paper_scenario_bar (session_id, market_time);

create table paper_contract_spec (
    session_id uuid not null references paper_session(id) on delete cascade,
    contract varchar(16) not null,
    volume_multiple integer not null check (volume_multiple > 0),
    price_tick numeric(20, 6) not null check (price_tick > 0),
    margin_per_lot numeric(20, 2) not null check (margin_per_lot > 0),
    commission_per_lot numeric(20, 6) not null check (commission_per_lot >= 0),
    primary key (session_id, contract)
);

create table paper_roll_event (
    id bigint generated always as identity primary key,
    session_id uuid not null references paper_session(id) on delete cascade,
    execution_date date not null,
    from_contract varchar(16) not null,
    to_contract varchar(16) not null,
    old_open numeric(20, 6) not null check (old_open > 0),
    new_open numeric(20, 6) not null check (new_open > 0),
    unique (session_id, execution_date, from_contract, to_contract)
);

create index paper_roll_event_session_date_idx on paper_roll_event (session_id, execution_date);

create table paper_order (
    id uuid primary key,
    session_id uuid not null references paper_session(id) on delete cascade,
    client_order_id varchar(128) not null,
    side varchar(8) not null check (side in ('BUY', 'SELL')),
    offset_type varchar(8) not null check (offset_type in ('OPEN', 'CLOSE')),
    order_type varchar(8) not null check (order_type in ('MARKET', 'LIMIT', 'STOP')),
    quantity integer not null check (quantity > 0),
    remaining_quantity integer not null check (remaining_quantity >= 0),
    limit_price numeric(20, 6),
    stop_price numeric(20, 6),
    status varchar(16) not null check (status in ('PENDING', 'PARTIAL', 'FILLED', 'CANCELLED', 'REJECTED')),
    rejection_reason varchar(240),
    eligible_bar_index integer not null check (eligible_bar_index >= 0),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (session_id, client_order_id),
    check ((order_type = 'LIMIT' and limit_price is not null and limit_price > 0) or order_type <> 'LIMIT'),
    check ((order_type = 'STOP' and stop_price is not null and stop_price > 0) or order_type <> 'STOP')
);

create index paper_order_session_created_idx on paper_order (session_id, created_at desc);
create index paper_order_pending_idx on paper_order (session_id, eligible_bar_index, created_at)
    where status in ('PENDING', 'PARTIAL');

create table paper_position (
    session_id uuid primary key references paper_session(id) on delete cascade,
    contract varchar(16) not null,
    direction smallint not null check (direction in (-1, 0, 1)),
    lots integer not null check (lots >= 0),
    average_price numeric(20, 6) not null check (average_price >= 0),
    margin_occupied numeric(20, 2) not null default 0 check (margin_occupied >= 0),
    unrealized_pnl numeric(20, 2) not null default 0,
    updated_at timestamptz not null default now(),
    check ((direction = 0 and lots = 0 and average_price = 0) or (direction <> 0 and lots > 0 and average_price > 0))
);

create table paper_fill (
    id uuid primary key,
    session_id uuid not null references paper_session(id) on delete cascade,
    order_id uuid references paper_order(id) on delete set null,
    event_type varchar(12) not null check (event_type in ('ORDER', 'ROLL')),
    contract varchar(16) not null,
    side varchar(8) not null check (side in ('BUY', 'SELL')),
    offset_type varchar(8) not null check (offset_type in ('OPEN', 'CLOSE')),
    quantity integer not null check (quantity > 0),
    market_price numeric(20, 6) not null check (market_price > 0),
    fill_price numeric(20, 6) not null check (fill_price > 0),
    fee numeric(20, 2) not null check (fee >= 0),
    slippage_cost numeric(20, 2) not null check (slippage_cost >= 0),
    realized_pnl numeric(20, 2) not null default 0,
    reason varchar(240) not null,
    market_time timestamptz not null,
    created_at timestamptz not null default now()
);

create index paper_fill_session_market_time_idx on paper_fill (session_id, market_time desc, created_at desc);
create index paper_fill_order_idx on paper_fill (order_id) where order_id is not null;
