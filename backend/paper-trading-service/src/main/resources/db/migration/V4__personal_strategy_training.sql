create table personal_strategy_version (
    id uuid primary key,
    parent_id uuid references personal_strategy_version(id),
    title varchar(120) not null,
    hypothesis text not null,
    validation_plan text not null,
    rules jsonb not null,
    engine_version varchar(40) not null,
    created_at timestamptz not null default now()
);

create table personal_training (
    session_id uuid primary key references paper_session(id) on delete cascade,
    version_id uuid not null references personal_strategy_version(id),
    training_mode varchar(20) not null check (training_mode in ('GUIDED','RULE_REPLAY')),
    training_start date not null,
    rules jsonb not null,
    stop_price numeric(20,6),
    risk_budget numeric(20,6) not null default 0,
    peak_equity numeric(20,2) not null,
    risk_halted boolean not null default false,
    entry_bar integer,
    last_exit_bar integer,
    created_at timestamptz not null default now()
);

create table personal_training_event (
    id uuid primary key,
    session_id uuid not null references personal_training(session_id) on delete cascade,
    command_id uuid not null,
    bar_index integer not null,
    market_time timestamptz not null,
    action varchar(16) not null,
    compliant boolean not null,
    emotion integer not null check (emotion between 0 and 5),
    notes varchar(4000) not null,
    plan jsonb not null,
    outcome jsonb not null,
    created_at timestamptz not null default now(),
    unique (session_id, command_id),
    unique (session_id, bar_index)
);
create index personal_event_session_page_idx on personal_training_event(session_id, bar_index desc);

create table personal_reflection (
    id uuid primary key,
    session_id uuid references personal_training(session_id) on delete cascade,
    event_id uuid references personal_training_event(id) on delete cascade,
    category varchar(20) not null,
    content varchar(5000) not null,
    created_at timestamptz not null default now()
);
create index personal_reflection_page_idx on personal_reflection(created_at desc,id desc);
