-- Replay runs and annotations are private to the account that created them.
create unique index if not exists strategy_workflow_version_tenant_id_unique
    on strategy_workflow_version(tenant_id,id);

create table paper_replay_review_run (
    id uuid primary key,
    tenant_id uuid not null default nullif(current_setting('app.tenant_id', true),'')::uuid,
    owner_id uuid not null default nullif(current_setting('app.user_id', true),'')::uuid,
    workflow_version_id uuid not null,
    snapshot_hash char(64) not null check (snapshot_hash ~ '^[a-f0-9]{64}$'),
    dataset_id char(64) not null check (dataset_id ~ '^[a-f0-9]{64}$'),
    symbol varchar(12) not null,
    initial_cash numeric(20,2) not null check (initial_cash > 0),
    cost_multiplier smallint not null check (cost_multiplier in (1,2)),
    timeline jsonb not null check (jsonb_typeof(timeline) = 'array' and jsonb_array_length(timeline) between 1 and 2000),
    executions jsonb not null check (jsonb_typeof(executions) = 'array' and jsonb_array_length(executions) <= 4000),
    created_at timestamptz not null default now(),
    unique(tenant_id,owner_id,id),
    unique(tenant_id,owner_id,workflow_version_id,symbol,initial_cash,cost_multiplier,snapshot_hash),
    foreign key(tenant_id,workflow_version_id) references strategy_workflow_version(tenant_id,id) on delete cascade
);

create table paper_replay_review (
    id uuid primary key,
    tenant_id uuid not null default nullif(current_setting('app.tenant_id', true),'')::uuid,
    owner_id uuid not null default nullif(current_setting('app.user_id', true),'')::uuid,
    client_request_id uuid not null,
    session_id uuid,
    run_id uuid,
    market_time timestamptz not null,
    stage varchar(8) not null check (stage in ('BAR','FILL')),
    target_id varchar(36),
    observed_action varchar(32) not null,
    suggested_action varchar(16) not null check (suggested_action in ('WAIT','OPEN_LONG','OPEN_SHORT','ADD','CLOSE','REDUCE')),
    reason varchar(2000) not null check (length(trim(reason)) > 0),
    evidence jsonb not null check (jsonb_typeof(evidence) = 'object'),
    created_at timestamptz not null default now(),
    check ((session_id is null) <> (run_id is null)),
    check ((stage = 'FILL') = (target_id is not null)),
    unique(tenant_id,owner_id,client_request_id),
    foreign key(tenant_id,session_id) references paper_session(tenant_id,id) on delete cascade,
    foreign key(tenant_id,owner_id,run_id) references paper_replay_review_run(tenant_id,owner_id,id) on delete cascade
);

create index paper_replay_review_session_market_idx on paper_replay_review(tenant_id,owner_id,session_id,market_time,created_at);
create index paper_replay_review_run_market_idx on paper_replay_review(tenant_id,owner_id,run_id,market_time,created_at);

alter table paper_replay_review_run enable row level security;
alter table paper_replay_review_run force row level security;
create policy paper_replay_run_owner on paper_replay_review_run using (
    tenant_id = nullif(current_setting('app.tenant_id',true),'')::uuid
    and owner_id = nullif(current_setting('app.user_id',true),'')::uuid
);

alter table paper_replay_review enable row level security;
alter table paper_replay_review force row level security;
create policy paper_replay_review_owner on paper_replay_review using (
    tenant_id = nullif(current_setting('app.tenant_id',true),'')::uuid
    and owner_id = nullif(current_setting('app.user_id',true),'')::uuid
    and (session_id is null or exists (
        select 1 from paper_session s
        where s.id = paper_replay_review.session_id and s.tenant_id = paper_replay_review.tenant_id
            and s.owner_id = paper_replay_review.owner_id
    ))
);
grant select, insert on paper_replay_review_run, paper_replay_review to aiquant_tenant;
