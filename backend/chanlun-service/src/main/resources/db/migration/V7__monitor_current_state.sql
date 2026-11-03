-- Preserve all existing immutable snapshots. Future non-event updates replace
-- only the current head, rather than creating another full historical copy.
alter table chanlun.monitor add column latest_analysis jsonb;
update chanlun.monitor m set latest_analysis=s.analysis
from chanlun.monitor_snapshot s where s.id=m.latest_snapshot_id;
