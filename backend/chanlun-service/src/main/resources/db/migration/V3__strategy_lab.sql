create table chanlun.lab_experiment (
    id uuid primary key,
    client_request_id uuid not null unique,
    request_payload jsonb not null,
    status varchar(16) not null check(status in ('RUNNING','SUCCEEDED','FAILED')),
    result jsonb,
    error varchar(400),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index lab_experiment_created on chanlun.lab_experiment(created_at desc,id);
