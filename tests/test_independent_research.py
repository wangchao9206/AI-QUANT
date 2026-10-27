"""Synthetic verification only. No production accounts or datasets are changed."""
from copy import deepcopy
from dataclasses import replace
from datetime import date,datetime,timedelta,timezone
import pytest
from backtesting.independent_research import ResearchRisk,causal_prices,hypothesis,planned_lots,simulate
from backtesting.workflow import compile_workflow
from data.data_feed import KLineBar
from data.tqsdk_backtest import FuturesContractSpec,RollEvent,TqSdkBacktestDataset

def dataset(count=100):
    bars=[KLineBar(datetime(2020,1,1,tzinfo=timezone.utc)+timedelta(days=i),100,101,99,100,100000,100000,'AA2001') for i in range(count)]
    return TqSdkBacktestDataset('AA0','ISOLATED','TEST_FIXTURE',bars[-1].timestamp,bars,[],
        {'AA2001':FuturesContractSpec('AA2001',100,1,1000,2)},True,bars)

def always_buy():
    nodes=[{'id':'market','type':'MARKET'},{'id':'price','type':'PRICE'},{'id':'zero','type':'CONSTANT'},
        {'id':'condition','type':'COMPARE'},{'id':'risk','type':'RISK','params':{'lots':1,'stopLossAtr':2,'takeProfitAtr':4}},
        {'id':'buy','type':'ACTION','params':{'action':'BUY'}}]
    edges=[]
    for a,ap,b,bp in [('market','bars','price','market'),('price','value','condition','left'),('zero','value','condition','right'),('condition','result','buy','condition'),('risk','risk','buy','risk')]:
        edges.append({'id':'e'+str(len(edges)),'source':a,'sourcePort':ap,'target':b,'targetPort':bp})
    return {'schemaVersion':1,'nodes':nodes,'edges':edges}

def run(d,cash=1_000_000,**kwargs):
    return simulate(d,always_buy(),cash,d.bars[1].timestamp.date(),d.bars[-1].timestamp.date(),**kwargs)

@pytest.mark.parametrize('family',['BREAKOUT','PULLBACK','REVERSION'])
def test_all_frozen_hypotheses_compile_without_unused_nodes(family):
    graph=hypothesis(family);program=compile_workflow(graph)
    assert len(graph['nodes'])<=40
    assert program.prepare(causal_prices(dataset())).evaluate(70).signal=='HOLD'

def test_insufficient_one_lot_budget_remains_flat_and_larger_accounts_size_down():
    d=dataset();small=run(d,10_000);large=run(d,1_000_000)
    assert small['metrics']['closedTrades']==0 and small['metrics']['returnPct']==0
    assert small['metrics']['denials']['RISK_OR_MARGIN_BELOW_ONE_LOT']>0
    assert large['trades'] and all(t['plannedRisk']<=t['riskBudget'] for t in large['trades'])

def test_signals_fill_on_next_bar_both_touch_stops_first_and_pnl_reconciles():
    d=dataset(4);d.bars[1].high=150;d.bars[1].low=70
    result=run(d)
    first=result['trades'][0]
    assert first['signalDate']=='2020-01-01' and first['entryDate']=='2020-01-02'
    assert first['exitReason']=='STOP' and first['netPnl']<0
    assert sum(t['netPnl'] for t in result['trades'])==pytest.approx(result['metrics']['netPnl'])

def test_roll_basis_is_not_cash_profit_and_future_rolls_do_not_rewrite_signals():
    d=dataset();i=50
    for b in d.bars[i:]:
        b.open*=2;b.high*=2;b.low*=2;b.close*=2;b.contract_symbol='AA2005'
    d=replace(d,contract_specs={**d.contract_specs,'AA2005':replace(d.contract_specs['AA2001'],contract='AA2005')},
        roll_events=[RollEvent(d.bars[i].timestamp.date(),'AA2001','AA2005',100,200,100,100)])
    signals=causal_prices(d)
    assert signals[49].close==signals[50].close==100
    result=run(d,risk=ResearchRisk(fee_rate=0,slippage_ticks=0))
    assert any(t['exitReason']=='ROLL_EXIT' for t in result['trades'])
    assert result['metrics']['netPnl']<=0
    assert signals[:40]==causal_prices(replace(d,bars=d.bars[:40],roll_events=[]))[:40]

def test_future_observations_cannot_change_a_completed_window():
    d=dataset();changed=deepcopy(d)
    for b in changed.bars[50:]:b.open*=3;b.high*=3;b.low*=3;b.close*=3
    a=simulate(d,always_buy(),1e6,date(2020,1,2),date(2020,2,9))
    b=simulate(changed,always_buy(),1e6,date(2020,1,2),date(2020,2,9))
    assert a==b

def test_cost_stress_reduces_net_profit_and_gap_losses_are_not_clipped_to_budget():
    d=dataset();base=run(d);stress=run(d,cost_multiplier=2)
    assert stress['metrics']['netPnl']<=base['metrics']['netPnl']
    g=dataset();g.bars[2].open=20;g.bars[2].low=19;g.bars[2].high=21;g.bars[2].close=20
    result=run(g)
    assert any(-t['netPnl']>t['riskBudget'] for t in result['trades'])
    assert result['metrics']['overBudgetExits']>0

def test_missing_roll_legs_and_bad_clocks_are_rejected():
    d=dataset();d.bars[-1].contract_symbol='AA2005'
    with pytest.raises(ValueError):causal_prices(d)
    d=dataset();d.bars[-1].timestamp=d.bars[-2].timestamp
    with pytest.raises(ValueError):causal_prices(d)
