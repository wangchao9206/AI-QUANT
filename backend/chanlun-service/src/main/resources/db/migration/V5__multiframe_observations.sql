create table chanlun.multiframe_run (
    id uuid primary key,
    client_request_id uuid not null unique,
    request_payload jsonb not null,
    status varchar(24) not null check(status in ('QUEUED','RUNNING','WAITING_INPUT','SUCCEEDED','FAILED')),
    result jsonb,
    error varchar(400),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index multiframe_run_created on chanlun.multiframe_run(created_at desc,id);
