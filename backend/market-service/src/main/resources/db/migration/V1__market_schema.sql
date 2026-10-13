create table market_quote_snapshot (
    id bigint generated always as identity primary key,
    symbol text not null,
    display_name text not null,
    price numeric(20, 6) not null check (price >= 0),
    price_change numeric(20, 6) not null,
    change_pct numeric(12, 6) not null,
    source text not null,
    observed_at timestamptz not null,
    created_at timestamptz not null default now(),
    constraint market_quote_snapshot_symbol_length check (char_length(symbol) between 2 and 12),
    constraint market_quote_snapshot_unique unique (symbol, source, observed_at)
);

create index market_quote_snapshot_symbol_observed_idx
    on market_quote_snapshot (symbol, observed_at desc);

create table market_term_snapshot (
    id bigint generated always as identity primary key,
    root_symbol text not null,
    contract_symbol text not null,
    maturity_date date not null,
    price numeric(20, 6) not null check (price >= 0),
    observed_at timestamptz not null,
    created_at timestamptz not null default now(),
    constraint market_term_snapshot_unique unique (contract_symbol, observed_at)
);

create index market_term_snapshot_root_observed_maturity_idx
    on market_term_snapshot (root_symbol, observed_at desc, maturity_date);
