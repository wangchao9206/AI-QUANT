create table market.live_monitor (
 id uuid primary key, tenant_id uuid not null, created_by uuid not null,
 asset_type varchar(10) not null check(asset_type in ('FUTURE','OPTION')),
 symbol varchar(100) not null, name varchar(80) not null, seconds integer not null check(seconds in (60,180,300,900)),
 parameters jsonb not null, metadata jsonb not null default '{}', enabled boolean not null default true,
 archived boolean not null default false, version bigint not null default 0,
 state jsonb not null default '{}', status varchar(20) not null default 'STARTING', message text not null default '',
 metrics jsonb not null default '{}', checked_at timestamptz, source_timestamp timestamptz,
 next_check_at timestamptz not null default now(), lease_owner uuid, lease_until timestamptz,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
 unique(tenant_id,id)
);
create index monitor_due on market.live_monitor(next_check_at) where enabled and not archived;
create index monitor_tenant_list on market.live_monitor(tenant_id,asset_type,created_at desc);
create table market.live_monitor_event (
 id bigint generated always as identity primary key, tenant_id uuid not null, monitor_id uuid not null,
 event_key varchar(300) not null, rule varchar(60) not null, label varchar(120) not null,
 symbol varchar(100) not null, asset_type varchar(10) not null, observed_at timestamptz not null,
 evidence jsonb not null, algorithm_version varchar(50) not null,
 acknowledged_at timestamptz, acknowledged_by uuid, created_at timestamptz not null default now(),
 foreign key(tenant_id,monitor_id) references market.live_monitor(tenant_id,id), unique(monitor_id,event_key)
);
create index monitor_event_tenant_page on market.live_monitor_event(tenant_id,asset_type,id desc);
create table market.live_monitor_audit (
 id bigint generated always as identity primary key, tenant_id uuid not null, monitor_id uuid not null,
 actor_id uuid not null, action varchar(30) not null, before_state jsonb, after_state jsonb,
 created_at timestamptz not null default now(), foreign key(tenant_id,monitor_id) references market.live_monitor(tenant_id,id)
);
do $$
declare tab text;
begin
 perform pg_advisory_xact_lock(71203002);
 if not exists(select 1 from pg_roles where rolname='aiquant_tenant') then
  create role aiquant_tenant nologin nosuperuser nocreatedb nocreaterole noinherit nobypassrls;
 end if;
 execute format('grant aiquant_tenant to %I',current_user);
 grant usage on schema market to aiquant_tenant;
 foreach tab in array array['live_monitor','live_monitor_event','live_monitor_audit'] loop
  execute format('alter table market.%I enable row level security',tab);
  execute format('alter table market.%I force row level security',tab);
  execute format('create policy tenant_private on market.%I using (tenant_id=nullif(current_setting(''app.tenant_id'',true),'''')::uuid) with check (tenant_id=nullif(current_setting(''app.tenant_id'',true),'''')::uuid)',tab);
 end loop;
 grant select,insert,update on market.live_monitor,market.live_monitor_event to aiquant_tenant;
 grant select,insert on market.live_monitor_audit to aiquant_tenant;
 grant usage,select on sequence market.live_monitor_event_id_seq,market.live_monitor_audit_id_seq to aiquant_tenant;
end $$;
