create table chanlun.replay_session (
    id uuid primary key,
    client_request_id uuid not null unique,
    request_payload jsonb not null,
    title varchar(120) not null,
    engine_id varchar(24) not null,
    dataset_id varchar(64) not null,
    dataset_hash varchar(64) not null,
    profile_hash varchar(64) not null,
    start_bars integer not null check(start_bars between 50 and 1893),
    observed_bars integer not null check(observed_bars between 50 and 1894),
    step integer not null default 0 check(step>=0),
    state varchar(16) not null default 'ACTIVE' check(state in ('ACTIVE','COMPLETE')),
    current_run_id uuid not null references chanlun.analysis_run(id),
    pending_command uuid,
    last_error varchar(400),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    check(observed_bars=start_bars+step)
);
create index replay_session_recent on chanlun.replay_session(created_at desc,id);
create table chanlun.replay_decision (
    id uuid primary key,
    client_request_id uuid not null unique,
    session_id uuid not null references chanlun.replay_session(id),
    step integer not null,
    observed_bars integer not null,
    run_id uuid not null references chanlun.analysis_run(id),
    judgment_id uuid not null unique references chanlun.judgment(id),
    request_payload jsonb not null,
    created_at timestamptz not null default now(),
    unique(session_id,step)
);
create table chanlun.replay_advance (
    id uuid primary key,
    client_request_id uuid not null unique,
    session_id uuid not null references chanlun.replay_session(id),
    expected_step integer not null,
    status varchar(16) not null check(status in ('RUNNING','SUCCEEDED','FAILED')),
    run_id uuid references chanlun.analysis_run(id),
    error varchar(400),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create unique index replay_one_advance_per_step on chanlun.replay_advance(session_id,expected_step) where status<>'FAILED';
