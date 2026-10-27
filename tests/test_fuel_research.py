from copy import deepcopy
from datetime import datetime,timedelta,timezone
import math
import pytest
from backtesting.fuel_research import FAMILIES,SCALES,REPAIRS,build,digest,segments,adjusted_sharpe_p,delayed_signals,choose_candidates
from backtesting.independent_research import simulate,causal_prices
from data.data_feed import KLineBar
from data.tqsdk_backtest import TqSdkBacktestDataset,FuturesContractSpec

def dataset(count=200):
    closes=[100+.03*i+5*math.sin(i/5) for i in range(count)]
    bars=[]
    for i,close in enumerate(closes):
        op=closes[max(0,i-1)]
        bars.append(KLineBar(datetime(2019,1,1,tzinfo=timezone.utc)+timedelta(days=i),
            op,max(op,close)+1,min(op,close)-1,close,20000+(i%5)*1000,20000,'FU1905'))
    return TqSdkBacktestDataset('FU0','ISOLATED','TEST_FIXTURE',bars[-1].timestamp,bars,[],
        {'FU1905':FuturesContractSpec('FU1905',10,1,1000,2)},True,bars)

@pytest.mark.parametrize('family',list(FAMILIES))
def test_frozen_configurations_compile_within_graph_budget(family):
    hashes=set()
    for repair in REPAIRS:
        for scale in SCALES:
            graph=build(family,scale,repair);hashes.add(digest(graph))
            assert len(graph['nodes'])<=40 and len(graph['edges'])<=120
    assert len(hashes)==9
    for direction in ['LONG','SHORT']:
        graph=build(family,direction=direction)
        actions=[n['params']['action'] for n in graph['nodes'] if n['type']=='ACTION']
        assert ('SELL' not in actions) if direction=='LONG' else ('BUY' not in actions)

@pytest.mark.parametrize('family',list(FAMILIES))
def test_future_changes_cannot_change_completed_fu_experiment(family):
    original=dataset();changed=deepcopy(original)
    for b in changed.bars[160:]:b.open*=5;b.high*=5;b.low*=5;b.close*=5
    start,end=original.bars[80].timestamp.date(),original.bars[149].timestamp.date()
    graph=build(family)
    assert simulate(original,graph,1e6,start,end)==simulate(changed,graph,1e6,start,end)

def test_delay_only_uses_preceding_observation_and_keeps_execution_clock():
    d=dataset();signals=causal_prices(d);delayed=delayed_signals(signals)
    assert [b.timestamp for b in delayed]==[b.timestamp for b in signals]
    assert all(delayed[i].close==signals[i-1].close for i in range(1,len(signals)))

def test_subperiod_returns_preserve_cash_and_are_not_independent_restarts():
    curve=[{'date':str(i),'equity':v} for i,v in enumerate([110,121,108.9,119.79,131.769,144.9459])]
    parts=segments(curve,100)
    assert math.prod(1+p['returnPct']/100 for p in parts)==pytest.approx(1.449459)
    assert parts[1]['returnPct']==pytest.approx(-1)

def test_joint_bootstrap_is_deterministic_and_zero_edge_not_significant():
    curves={name:[{'date':str(i),'equity':100.} for i in range(30)] for name in ['a','b']}
    a=adjusted_sharpe_p(curves,100,['a'],iterations=50)
    assert a==adjusted_sharpe_p(curves,100,['a'],iterations=50)
    assert a['selected']['a']['adjustedP']==1
    assert type(a['selected']['a']['adjustedP']) is float
    import json
    json.dumps({'gate':a['selected']['a']['adjustedP']<=.1})
    curves['b'][0]['date']='wrong-clock'
    with pytest.raises(ValueError,match='clocks'):adjusted_sharpe_p(curves,100,['a'],iterations=5)

def test_validation_cannot_be_passed_to_development_selector():
    with pytest.raises(ValueError,match='development'):choose_candidates([{'stage':'VALIDATION'}])
