-- No record or balance is deleted. Ambiguous legacy ownership stays inaccessible.
alter table paper_session add column if not exists owner_id uuid default nullif(current_setting('app.user_id',true),'')::uuid;
alter table personal_reflection add column if not exists owner_id uuid default nullif(current_setting('app.user_id',true),'')::uuid;
alter table personal_strategy_version add column if not exists owner_id uuid default nullif(current_setting('app.user_id',true),'')::uuid;

do $$
declare target text; creation_path text;
begin
 if to_regclass('identity.operation_log') is not null then
  foreach target in array array['paper_session','personal_reflection','personal_strategy_version'] loop
   creation_path:=case target when 'paper_session' then '/api/v1/paper/sessions' when 'personal_reflection' then '/api/v1/paper/personal/reflections' else '/api/v1/paper/personal/versions' end;
   execute format($sql$
    with candidates as (
     select s.id,(array_agg(distinct o.user_id))[1] as creator
     from %I s join identity.operation_log o on o.tenant_id=s.tenant_id
       and o.method='POST' and o.path=%L and o.status between 200 and 299 and o.user_id is not null
       and s.created_at between o.created_at-(o.duration_ms+3000)*interval '1 millisecond' and o.created_at+interval '1 second'
     where s.owner_id is null group by s.id having count(distinct o.user_id)=1
    ) update %I s set owner_id=c.creator from candidates c where s.id=c.id and s.owner_id is null
   $sql$,target,creation_path,target);
  end loop;
 end if;
 -- Decision sessions already have a private, verified creator binding.
 update paper_session s set owner_id=p.owner_id from decision_paper p
 where s.id=p.session_id and s.tenant_id=p.tenant_id and s.owner_id is null;
 update personal_reflection r set owner_id=s.owner_id from paper_session s
 where r.session_id=s.id and r.tenant_id=s.tenant_id and r.owner_id is null;
end $$;

create index if not exists paper_session_private_owner on paper_session(tenant_id,owner_id,updated_at desc);
drop policy if exists paper_private_owner on paper_session;
create policy paper_private_owner on paper_session as restrictive
 using(owner_id=nullif(current_setting('app.user_id',true),'')::uuid)
 with check(owner_id=nullif(current_setting('app.user_id',true),'')::uuid);

do $$
declare item record; target text;
begin
 for item in select table_name from information_schema.columns where table_schema=current_schema() and column_name='session_id' loop
  execute format('drop policy if exists private_parent_account on %I',item.table_name);
  execute format('create policy private_parent_account on %I as restrictive using (%s) with check (%s)',item.table_name,
   format('exists(select 1 from paper_session s where s.id=session_id and s.tenant_id=%I.tenant_id)',item.table_name),
   format('exists(select 1 from paper_session s where s.id=session_id and s.tenant_id=%I.tenant_id)',item.table_name));
 end loop;
 -- Reflections may be standalone; ownership applies even without a session.
 drop policy if exists private_parent_account on personal_reflection;
 create policy private_parent_account on personal_reflection as restrictive
  using(session_id is null or exists(select 1 from paper_session s where s.id=session_id and s.tenant_id=personal_reflection.tenant_id))
  with check(session_id is null or exists(select 1 from paper_session s where s.id=session_id and s.tenant_id=personal_reflection.tenant_id));
 foreach target in array array['personal_reflection','personal_strategy_version'] loop
  execute format('drop policy if exists private_author on %I',target);
  execute format('create policy private_author on %I as restrictive using(owner_id=nullif(current_setting(''app.user_id'',true),'''')::uuid) with check(owner_id=nullif(current_setting(''app.user_id'',true),'''')::uuid)',target);
 end loop;
end $$;
drop policy if exists private_parent_run on paper_automation_event;
create policy private_parent_run on paper_automation_event as restrictive
 using(exists(select 1 from paper_automation_run r where r.id=run_id and r.tenant_id=paper_automation_event.tenant_id))
 with check(exists(select 1 from paper_automation_run r where r.id=run_id and r.tenant_id=paper_automation_event.tenant_id));

-- A task created through the old shared boundary cannot trade another owner's wallet.
update paper_automation_run r set enabled=false,status='FORBIDDEN',message='账户归属隔离已升级，原运行身份不匹配，已停止；持仓保留',
 lease_owner=null,lease_until=null,revision=revision+1
from paper_session s where r.session_id=s.id and r.tenant_id=s.tenant_id and r.enabled and r.owner_id is distinct from s.owner_id;
update paper_order o set status='CANCELLED',reserved_cash=0,updated_at=now()
from paper_automation_run r,paper_session s
where o.automation_run_id=r.id and r.session_id=s.id and r.tenant_id=s.tenant_id
 and r.owner_id is distinct from s.owner_id and o.status in ('PENDING','PARTIAL');
