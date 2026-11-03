alter table chanlun.analysis_run drop constraint analysis_run_observed_bars_check;
-- Public worker calculations still start at 50; archived observation-derived
-- prefixes can include the first difference before that warmup boundary.
alter table chanlun.analysis_run add constraint analysis_run_observed_bars_check check(observed_bars between 1 and 10000);
create table chanlun.comparison (
    id uuid primary key,
    client_request_id uuid not null unique,
    request_payload jsonb not null,
    status varchar(16) not null check(status in ('RUNNING','SUCCEEDED','FAILED')),
    result jsonb,
    error varchar(400),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create table chanlun.comparison_member (
    comparison_id uuid not null references chanlun.comparison(id),
    run_id uuid not null references chanlun.analysis_run(id),
    primary key(comparison_id,run_id)
);
create index comparison_created on chanlun.comparison(created_at desc,id);
