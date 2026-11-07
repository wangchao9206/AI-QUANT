-- Existing fills/positions remain immutable. A missing private binding must never mean unguarded.
alter table paper_trading.paper_session add column decision_guarded boolean not null default false;
update paper_trading.paper_session s set decision_guarded=true
where exists(select 1 from paper_trading.decision_paper d where d.session_id=s.id and d.tenant_id=s.tenant_id);
