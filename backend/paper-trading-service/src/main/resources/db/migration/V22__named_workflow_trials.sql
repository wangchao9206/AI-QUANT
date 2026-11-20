alter table paper_replay_review_run
    add column trial_name varchar(80),
    add column trial_request_id uuid,
    add column trial_summary jsonb,
    add constraint paper_replay_trial_request_unique unique(tenant_id,owner_id,trial_request_id),
    add constraint paper_replay_trial_metadata check (
        (trial_name is null and trial_request_id is null and trial_summary is null) or
        (trial_name is not null and length(trim(trial_name)) > 0 and trial_request_id is not null
            and trial_summary is not null and jsonb_typeof(trial_summary) = 'object')
    );

create index paper_replay_trial_owner_created_idx
    on paper_replay_review_run(tenant_id,owner_id,created_at desc,id desc) where trial_name is not null;
