create table chanlun.analysis_run (
    id uuid primary key,
    client_request_id uuid not null unique,
    engine_id varchar(24) not null,
    dataset_id varchar(64) not null,
    observed_bars integer not null check (observed_bars between 50 and 5000),
    status varchar(24) not null check (status in ('QUEUED','RUNNING','SUCCEEDED','FAILED')),
    result jsonb,
    error varchar(400),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index analysis_run_created on chanlun.analysis_run(created_at desc,id);
create table chanlun.structure_event (
    run_id uuid not null references chanlun.analysis_run(id),
    event_seq integer not null,
    structure_id varchar(24) not null,
    payload jsonb not null,
    primary key(run_id,event_seq)
);
create index structure_event_lookup on chanlun.structure_event(run_id,structure_id,event_seq desc);
create table chanlun.judgment (
    id uuid primary key,
    client_request_id uuid not null unique,
    run_id uuid not null references chanlun.analysis_run(id),
    structure_id varchar(24),
    outlook varchar(8) not null check (outlook in ('UP','DOWN','WAIT')),
    content text not null check(length(content) between 1 and 6000),
    evidence jsonb not null,
    created_at timestamptz not null default now()
);
create index judgment_created on chanlun.judgment(created_at desc,id);
