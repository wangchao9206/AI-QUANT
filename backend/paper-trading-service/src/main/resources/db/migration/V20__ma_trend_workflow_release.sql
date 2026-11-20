alter table strategy_workflow_version drop constraint strategy_workflow_version_lots_check;
alter table strategy_workflow_version drop constraint strategy_workflow_version_stop_loss_atr_check;
alter table strategy_workflow_version drop constraint strategy_workflow_version_take_profit_atr_check;

alter table strategy_workflow_version add constraint strategy_workflow_version_risk_check check (
    case
        when engine_version = 'workflow-ma-trend-15m-v1' then
            lots = 0 and stop_loss_atr = 0 and take_profit_atr = 0
        else
            lots between 1 and 1000000 and stop_loss_atr between 0.1 and 20 and take_profit_atr between 0.1 and 50
    end
);
