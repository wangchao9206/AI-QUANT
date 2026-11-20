alter table paper_session add column if not exists multi_instrument boolean not null default false;
alter table paper_session add column if not exists portfolio_valued_at timestamptz;
alter table paper_order add column if not exists contract varchar(16);
alter table paper_order add column if not exists reserved_cash numeric(20,2) not null default 0 check (reserved_cash >= 0);

create unique index paper_session_portfolio_parent on paper_session(tenant_id,id);
create table paper_portfolio_position (
    tenant_id uuid not null default nullif(current_setting('app.tenant_id',true),'')::uuid,
    session_id uuid not null,
    contract varchar(16) not null check (contract ~ '^[A-Z]{1,4}[0-9]{3,4}$'),
    symbol varchar(12) not null,
    direction smallint not null default 0 check (direction in (-1,0,1)),
    lots integer not null default 0 check (lots >= 0),
    average_price numeric(20,6) not null default 0 check (average_price >= 0),
    current_price numeric(20,6) not null check (current_price > 0),
    market_time timestamptz not null,
    market_state varchar(24) not null default 'UNKNOWN',
    data_source varchar(120) not null,
    volume_multiple integer not null check (volume_multiple > 0),
    price_tick numeric(20,6) not null check (price_tick > 0),
    margin_per_lot numeric(20,2) not null check (margin_per_lot > 0),
    commission_per_lot numeric(20,6) not null check (commission_per_lot >= 0),
    margin_occupied numeric(20,2) not null default 0 check (margin_occupied >= 0),
    unrealized_pnl numeric(20,2) not null default 0,
    updated_at timestamptz not null default now(),
    primary key (tenant_id,session_id,contract),
    foreign key (tenant_id,session_id) references paper_session(tenant_id,id) on delete cascade,
    check ((direction=0 and lots=0 and average_price=0) or (direction<>0 and lots>0 and average_price>0))
);
create index paper_portfolio_open_positions on paper_portfolio_position(tenant_id,session_id) where lots>0;
create index paper_order_contract_pending on paper_order(tenant_id,session_id,contract) where status in ('PENDING','PARTIAL');
alter table paper_portfolio_position enable row level security;
alter table paper_portfolio_position force row level security;
create policy tenant_private on paper_portfolio_position
    using (tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid)
    with check (tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid);
grant select,insert,update,delete on paper_portfolio_position to aiquant_tenant;
