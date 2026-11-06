create table identity.account (
 id uuid primary key, username varchar(32) not null unique, email varchar(254) unique,
 password_hash varchar(100) not null, verified boolean not null default false,
 must_change boolean not null default true, platform_admin boolean not null default false,
 enabled boolean not null default true, created_at timestamptz not null default now()
);
create table identity.tenant (
 id uuid primary key, name varchar(80) not null, enabled boolean not null default true,
 created_at timestamptz not null default now()
);
create table identity.membership (
 tenant_id uuid not null references identity.tenant(id), user_id uuid not null references identity.account(id),
 role varchar(10) not null check(role in ('OWNER','ADMIN','MEMBER','VIEWER')), primary key(tenant_id,user_id)
);
create table identity.session (
 id uuid primary key, token_hash char(64) not null unique, csrf_hash char(64) not null,
 user_id uuid not null references identity.account(id), tenant_id uuid not null references identity.tenant(id),
 expires_at timestamptz not null, created_at timestamptz not null default now()
);
create index identity_session_user_idx on identity.session(user_id);
create table identity.challenge (
 token_hash char(64) primary key, user_id uuid not null references identity.account(id),
 purpose varchar(10) not null check(purpose in ('VERIFY','RESET','EMAIL')), target_email varchar(254), expires_at timestamptz not null,
 created_at timestamptz not null default now()
);
create table identity.api_key (
 id uuid primary key, tenant_id uuid not null references identity.tenant(id),
 user_id uuid not null references identity.account(id), name varchar(80) not null,
 token_hash char(64) not null unique, scope varchar(16) not null check(scope in ('READ','READ_WRITE')),
 expires_at timestamptz not null, created_at timestamptz not null default now()
);
create table identity.external_identity (
 provider varchar(100) not null, subject varchar(255) not null,
 user_id uuid not null references identity.account(id), primary key(provider,subject)
);
create table identity.audit (
 id bigint generated always as identity primary key, user_id uuid, tenant_id uuid,
 action varchar(64) not null, target varchar(128), created_at timestamptz not null default now()
);
create table identity.rate_limit (
 key_hash char(64) not null, bucket bigint not null, attempts integer not null,
 primary key(key_hash,bucket)
);
