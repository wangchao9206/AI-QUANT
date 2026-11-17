alter table paper_session add column if not exists bar_seconds integer not null default 86400 check (bar_seconds in (60,180,300,900,86400));
alter table paper_session add column if not exists intraday_only boolean not null default false;
alter table paper_session add column if not exists stop_loss_ticks integer not null default 0 check (stop_loss_ticks between 0 and 10000);
alter table paper_session add column if not exists replay_context jsonb not null default '{}'::jsonb;

create unique index paper_fill_tenant_session_identity on paper_fill(tenant_id,session_id,id);
create table paper_fill_note (
    tenant_id uuid not null default nullif(current_setting('app.tenant_id',true),'')::uuid,
    session_id uuid not null,
    fill_id uuid not null,
    owner_id uuid not null,
    content varchar(6000) not null default '',
    version integer not null check (version>0),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key(tenant_id,fill_id,owner_id),
    foreign key(tenant_id,session_id,fill_id) references paper_fill(tenant_id,session_id,id) on delete cascade
);
create index paper_fill_note_session_owner on paper_fill_note(tenant_id,session_id,owner_id);
alter table paper_fill_note enable row level security;
alter table paper_fill_note force row level security;
create policy tenant_private on paper_fill_note
    using (tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid)
    with check (tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid);
create policy note_owner on paper_fill_note as restrictive
    using (owner_id=nullif(current_setting('app.user_id',true),'')::uuid)
    with check (owner_id=nullif(current_setting('app.user_id',true),'')::uuid);
grant select,insert,update,delete on paper_fill_note to aiquant_tenant;
