create table strategy_decision_snapshot (
    id bigint generated always as identity primary key,
    symbol text not null,
    model_version text not null,
    input_timestamp timestamptz not null,
    calculated_at timestamptz not null,
    data_status text not null,
    trace_id text not null,
    result_payload jsonb not null,
    created_at timestamptz not null default now(),
    constraint strategy_decision_symbol_length check (char_length(symbol) between 2 and 12),
    constraint strategy_decision_status check (data_status in ('FRESH', 'CACHED', 'DEGRADED')),
    constraint strategy_decision_unique unique (symbol, model_version, input_timestamp)
);

create index strategy_decision_symbol_calculated_idx
    on strategy_decision_snapshot (symbol, calculated_at desc);

create index strategy_decision_trace_idx
    on strategy_decision_snapshot (trace_id);
