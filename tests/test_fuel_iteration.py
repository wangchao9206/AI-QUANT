import pytest
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from backtesting.fuel_iteration import FAMILIES,MODES,regime_graph
from backtesting.fuel_research import SCALES
from backtesting.workflow import compile_workflow
from data.data_feed import KLineBar

@pytest.mark.parametrize('family',FAMILIES)
@pytest.mark.parametrize('mode',MODES)
def test_iteration_graphs_compile_and_never_change_earlier_signals(family,mode):
    bars=[KLineBar(datetime(2020,1,1,tzinfo=timezone.utc)+timedelta(days=i),
        100+i,101+i,99+i,100+i,10000,10000,'FU2005') for i in range(150)]
    changed=deepcopy(bars)
    for b in changed[110:]:b.open*=3;b.close*=3;b.high*=3;b.low*=3
    for scale in SCALES:
        program=compile_workflow(regime_graph(family,mode,scale))
        assert len(program.nodes)<=40
        assert program.prepare(bars).evaluate(100,-1)==program.prepare(changed).evaluate(100,-1)

def test_regime_exit_closes_an_adverse_trend_that_entry_gate_alone_does_not():
    bars=[KLineBar(datetime(2020,1,1,tzinfo=timezone.utc)+timedelta(days=i),
        100+i,101+i,99+i,100+i,10000,10000,'FU2005') for i in range(150)]
    entry_only=compile_workflow(regime_graph('RANGE_REVERSION','RANGE_GATE')).prepare(bars).evaluate(100,-1)
    with_exit=compile_workflow(regime_graph('RANGE_REVERSION','REGIME_EXIT')).prepare(bars).evaluate(100,-1)
    assert entry_only.signal=='HOLD'
    assert with_exit.signal=='FLATTEN'
