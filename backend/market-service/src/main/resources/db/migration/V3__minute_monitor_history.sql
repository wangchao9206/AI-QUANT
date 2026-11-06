alter table market.live_monitor add column next_history_at timestamptz not null default now();
create table market.live_monitor_history (
 id bigint generated always as identity primary key,
 tenant_id uuid not null, monitor_id uuid not null, monitor_version bigint not null,
 asset_type varchar(10) not null, symbol varchar(100) not null, name varchar(80) not null,
 seconds integer not null, parameters jsonb not null,
 checked_at timestamptz not null default now(), source_timestamp timestamptz,
 status varchar(20) not null, message text not null,
 metrics jsonb not null, signals jsonb not null, algorithm_version varchar(80) not null,
 foreign key(tenant_id,monitor_id) references market.live_monitor(tenant_id,id)
);
create index monitor_history_tenant_page on market.live_monitor_history(tenant_id,asset_type,id desc);
create index monitor_history_job_page on market.live_monitor_history(tenant_id,monitor_id,id desc);
alter table market.live_monitor_history enable row level security;
alter table market.live_monitor_history force row level security;
create policy tenant_private on market.live_monitor_history
 using (tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid)
 with check (tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid);
grant select on market.live_monitor_history to aiquant_tenant;
