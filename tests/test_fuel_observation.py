from copy import deepcopy
from dataclasses import replace
from datetime import datetime,timedelta,timezone
import pytest
from backtesting.fuel_observation import freeze,advance,atomic_save,state_lock
from data.data_feed import KLineBar
from data.tqsdk_backtest import TqSdkBacktestDataset,FuturesContractSpec

def source(n):
    bars=[KLineBar(datetime(2020,1,1,tzinfo=timezone.utc)+timedelta(days=i),100,101,99,100,100000,100000,'FU2005') for i in range(n)]
    return TqSdkBacktestDataset('FU0','ISOLATED','TEST_FIXTURE',bars[-1].timestamp,bars,[],
         {'FU2005':FuturesContractSpec('FU2005',100,1,1000,2)},True,bars)
def graph():
    nodes=[{'id':'m','type':'MARKET'},{'id':'p','type':'PRICE'},{'id':'z','type':'CONSTANT'},
      {'id':'c','type':'COMPARE'},{'id':'r','type':'RISK','params':{'lots':1,'stopLossAtr':2,'takeProfitAtr':4}},
      {'id':'a','type':'ACTION','params':{'action':'BUY'}}];edges=[]
    for a,ap,b,bp in [('m','bars','p','market'),('p','value','c','left'),('z','value','c','right'),('c','result','a','condition'),('r','risk','a','risk')]:
        edges.append({'id':'e'+str(len(edges)),'source':a,'sourcePort':ap,'target':b,'targetPort':bp})
    return {'schemaVersion':1,'nodes':nodes,'edges':edges}

def test_open_position_survives_each_new_bar_and_no_terminal_fill_is_fabricated():
    initial=freeze(source(50),graph())
    first=advance(initial,source(51))
    second=advance(first,source(52))
    direct=advance(initial,source(52))
    assert first['position'] and second['position']
    assert first['trades']==second['trades']==[]
    assert second['cash']==pytest.approx(direct['cash'])
    assert second['equity']==pytest.approx(direct['equity'])
    assert second['curve'][:1]==first['curve']
    assert second['position']['entryDate']=='2020-02-20'
    assert second['ordersSubmittedToBroker']==0

def test_repeated_snapshot_is_idempotent_and_retroactive_edits_are_rejected():
    state=advance(freeze(source(50),graph()),source(51))
    assert advance(state,source(51)) is state
    edited=source(52)
    for field in ['open','high','low','close']:setattr(edited.bars[0],field,getattr(edited.bars[0],field)*1.01)
    with pytest.raises(ValueError,match='evidence'):advance(state,edited)
    tampered=deepcopy(state);tampered['config']['risk']['fraction']=.02
    with pytest.raises(ValueError,match='configuration'):advance(tampered,source(52))

def test_actual_stop_remains_and_incremental_matches_single_replay():
    initial=freeze(source(50),graph());one=advance(initial,source(51));two_source=source(52)
    two_source.bars[-1].low=90
    two=advance(one,two_source);direct=advance(initial,two_source)
    assert two['position'] is None
    assert len(two['trades'])==1 and two['trades'][0]['exitReason']=='STOP'
    assert two['equity']==pytest.approx(direct['equity'])
    assert two['equity']==pytest.approx(initial['equity']+two['realizedClosedNetPnl'])

def test_shadow_store_is_locked_and_atomic(tmp_path):
    path=tmp_path/'state.json';state=freeze(source(50),graph())
    with state_lock(path):
        with pytest.raises(FileExistsError):
            with state_lock(path):pass
        atomic_save(path,state)
    assert path.exists() and not list(tmp_path.glob('*.lock'))
    assert not list(tmp_path.glob('*.tmp'))
