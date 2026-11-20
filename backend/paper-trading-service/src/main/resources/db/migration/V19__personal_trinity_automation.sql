alter table paper_automation_run drop constraint paper_automation_run_strategy_check;
alter table paper_automation_run add constraint paper_automation_run_strategy_check check (
    strategy in ('MA20_MACD','HOLISTIC_14D','MOMENTUM_BREAKOUT','BOLLINGER_REVERSAL','DUAL_THRUST',
                 'ADAPTIVE_CTA','BUY_AND_HOLD','WORKFLOW','PERSONAL_TRINITY')
);
alter table paper_automation_run add column trinity_config jsonb;
alter table paper_automation_run add constraint paper_automation_trinity_config_check check (
    (strategy = 'PERSONAL_TRINITY') = (trinity_config is not null)
    and (trinity_config is null or jsonb_typeof(trinity_config) = 'object')
);
