create table chanlun.monitor (
    id uuid primary key,
    client_request_id uuid not null unique,
    request_payload jsonb not null,
    title varchar(120) not null,
    symbol varchar(12) not null,
    frequency varchar(8) not null check(frequency in ('DAY','MIN5','MIN30')),
    enabled boolean not null default true,
    status varchar(32) not null default 'WAITING_DATA',
    profile_hash varchar(64),
    bars jsonb not null default '[]'::jsonb,
    observed_bars integer not null default 0 check(observed_bars between 0 and 10000),
    last_event_seq integer not null default 0,
    source jsonb,
    last_error varchar(400),
    heartbeat_at timestamptz,
    next_check_at timestamptz not null default now(),
    lease_id uuid,
    lease_until timestamptz,
    latest_snapshot_id uuid,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index monitor_due on chanlun.monitor(next_check_at) where enabled;
create table chanlun.monitor_snapshot (
    id uuid primary key,
    monitor_id uuid not null references chanlun.monitor(id),
    input_hash varchar(64) not null,
    profile_hash varchar(64) not null,
    analysis jsonb not null,
    source jsonb not null,
    created_at timestamptz not null default now(),
    unique(monitor_id,input_hash,profile_hash)
);
alter table chanlun.monitor add foreign key(latest_snapshot_id) references chanlun.monitor_snapshot(id);
create table chanlun.monitor_event (
    monitor_id uuid not null references chanlun.monitor(id),
    event_seq integer not null,
    structure_id varchar(24) not null,
    snapshot_id uuid not null references chanlun.monitor_snapshot(id),
    payload jsonb not null,
    inbox_state varchar(32) not null check(inbox_state in ('NEW','ACKNOWLEDGED','SUPPRESSED_BOOTSTRAP','SUPPRESSED_BACKFILL','SUPPRESSED_CLOSED')),
    detected_at timestamptz not null default now(),
    primary key(monitor_id,event_seq)
);
create index monitor_event_inbox on chanlun.monitor_event(inbox_state,detected_at desc);
create table chanlun.monitor_review (
    id uuid primary key,
    client_request_id uuid not null unique,
    monitor_id uuid not null,
    event_seq integer not null,
    outlook varchar(8) not null check(outlook in ('UP','DOWN','WAIT')),
    content text not null check(length(content) between 1 and 6000),
    lesson_number integer check(lesson_number between 1 and 108),
    evidence jsonb not null,
    created_at timestamptz not null default now(),
    foreign key(monitor_id,event_seq) references chanlun.monitor_event(monitor_id,event_seq)
);
