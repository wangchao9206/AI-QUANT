alter table identity.account add column display_name varchar(80) not null default '';
alter table identity.audit add column before_state jsonb;
alter table identity.audit add column after_state jsonb;
create index audit_tenant_page on identity.audit(tenant_id,id desc);
create table identity.access_role (
 id uuid primary key, tenant_id uuid not null references identity.tenant(id),
 name varchar(80) not null, description varchar(400) not null default '',
 permissions jsonb not null default '[]', enabled boolean not null default true,
 version bigint not null default 0, created_at timestamptz not null default now(),
 unique(tenant_id,name),unique(id,tenant_id)
);
create table identity.role_assignment (
 tenant_id uuid not null, user_id uuid not null, role_id uuid not null,
 primary key(tenant_id,user_id,role_id),
 foreign key(tenant_id,user_id) references identity.membership(tenant_id,user_id) on delete cascade,
 foreign key(role_id,tenant_id) references identity.access_role(id,tenant_id) on delete cascade
);
create table identity.menu (
 id uuid primary key, parent_id uuid references identity.menu(id),
 label varchar(80) not null, path varchar(100) unique, permission varchar(80) not null,
 sort_order integer not null default 0, enabled boolean not null default true,
 version bigint not null default 0
);
insert into identity.menu(id,label,path,permission,sort_order) values
 ('10000000-0000-0000-0000-000000000001','总览','/overview','overview.read',10),
 ('10000000-0000-0000-0000-000000000002','消息','/news','news.read',20),
 ('10000000-0000-0000-0000-000000000003','线索池','/leads','leads.read',30),
 ('10000000-0000-0000-0000-000000000004','市场','/market','market.read',40),
 ('10000000-0000-0000-0000-000000000005','期权','/options','options.read',50),
 ('10000000-0000-0000-0000-000000000006','缠论','/chanlun','chanlun.read',60),
 ('10000000-0000-0000-0000-000000000007','策略','/strategy','workflows.read',70),
 ('10000000-0000-0000-0000-000000000008','自主研究','/research','research.read',80),
 ('10000000-0000-0000-0000-000000000009','学习','/learn','learn.read',90),
 ('10000000-0000-0000-0000-000000000010','大佬解读','/mentors','mentors.read',100),
 ('10000000-0000-0000-0000-000000000011','个人总结','/personal','personal.read',110),
 ('10000000-0000-0000-0000-000000000012','书籍感悟','/books','books.read',120),
 ('10000000-0000-0000-0000-000000000013','回测模拟','/backtest','backtest.read',130),
 ('10000000-0000-0000-0000-000000000014','模拟交易','/paper','paper.read',140),
 ('10000000-0000-0000-0000-000000000015','系统','/system','system.read',150);
create table identity.operation_log (
 id bigint generated always as identity primary key,
 user_id uuid, tenant_id uuid, method varchar(10) not null, path varchar(300) not null,
 status integer not null, duration_ms bigint not null, trace_id varchar(128),
 created_at timestamptz not null default now()
);
create index operation_tenant_page on identity.operation_log(tenant_id,id desc);
