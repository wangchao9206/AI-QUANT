-- Preserve definitions and evidence. Pure legacy jobs are archived; mixed jobs
-- keep only the newer opportunity alerts. Versions invalidate in-flight work.
with selected as (
 select id, coalesce((select jsonb_agg(rule order by ord)
   from jsonb_array_elements_text(parameters->'rules') with ordinality as r(rule,ord)
   where rule in ('OUTCOME_PATTERN','DAILY_RESEARCH_CONTEXT',
     'DAILY_MA_BREAKOUT_UP','DAILY_MA_BREAKOUT_DOWN','DAILY_MA_PULLBACK')), '[]'::jsonb) as rules
 from market.live_monitor where not archived
), retired as (
 select s.* from selected s join market.live_monitor m using(id)
 where s.rules is distinct from m.parameters->'rules'
)
update market.live_monitor m set
 parameters=case when r.rules='[]'::jsonb then m.parameters else jsonb_set(m.parameters,'{rules}',r.rules) end,
 archived=(r.rules='[]'::jsonb), enabled=m.enabled and r.rules<>'[]'::jsonb,
 status=case when m.enabled and r.rules<>'[]'::jsonb then 'STARTING' else 'PAUSED' end,
 message='旧盘口定时扫描已下线',version=m.version+1,state='{}',metrics='{}',
 lease_owner=null,lease_until=null,next_check_at=now(),updated_at=now()
from retired r where m.id=r.id;

alter table market.live_monitor add constraint active_opportunity_rules check (
 archived or (jsonb_typeof(parameters->'rules')='array'
 and jsonb_array_length(parameters->'rules')>0
 and parameters->'rules' <@ '["OUTCOME_PATTERN","DAILY_RESEARCH_CONTEXT","DAILY_MA_BREAKOUT_UP","DAILY_MA_BREAKOUT_DOWN","DAILY_MA_PULLBACK"]'::jsonb
 and parameters ? 'rules')
);
