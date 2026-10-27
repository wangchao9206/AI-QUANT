from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from algorithm_service.app import app
from algorithm_service.paper_strategy import StrategyRequest, evaluate, live_context

client=TestClient(app)


def rows(count=70, drop=False):
    start=datetime(2025,1,1,tzinfo=timezone.utc)
    result=[]
    for index in range(count):
        price=100+index*.1
        if drop and index==count-1: price=70
        result.append({'timestamp':(start+timedelta(days=index)).isoformat(),'open':price,
            'high':price+1,'low':price-1,'close':price,'volume':1000,'openInterest':100})
    return result


def body(strategy='BOLLINGER_REVERSAL',bars=None):
    data=bars or rows(drop=True)
    return {'strategy':strategy,'symbol':'JM0','asOf':data[-1]['timestamp'],
            'bars':data,'executionBars':data,'direction':0}


def test_paper_strategy_rejects_future_information_and_unknown_strategy():
    data=body()
    baseline=evaluate(StrategyRequest.model_validate(data))
    future={**data['bars'][-1],'timestamp':'2030-01-01T00:00:00Z','close':9999,'high':10000,'open':9999,'low':9998}
    changed=evaluate(StrategyRequest.model_validate({**data,'bars':data['bars']+[future]}))
    assert baseline==changed
    assert baseline['signal']=='BUY'
    assert baseline['atr']>0
    assert client.post('/internal/v1/simulation/strategy/evaluate',json={**data,'strategy':'FAKE'}).status_code==422


@pytest.mark.parametrize('strategy',['HOLISTIC_14D','MOMENTUM_BREAKOUT','BOLLINGER_REVERSAL','DUAL_THRUST','ADAPTIVE_CTA','BUY_AND_HOLD'])
def test_all_selectable_strategies_evaluate_bounded_daily_observations(strategy):
    response=client.post('/internal/v1/simulation/strategy/evaluate',json=body(strategy))
    assert response.status_code==200
    result=response.json()
    assert result['strategy']==strategy
    assert result['signal'] in ['BUY','SELL','HOLD','FLATTEN']
    assert result['historyCount']==70


def test_strategy_warmup_flat_market_exit_and_buy_hold_dedup():
    assert evaluate(StrategyRequest.model_validate(body('MOMENTUM_BREAKOUT',rows(20))))['signal']=='WARMING'
    flat=[{**row,'open':100,'high':100,'low':100,'close':100} for row in rows()]
    assert evaluate(StrategyRequest.model_validate(body(bars=flat)))['signal']=='HOLD'
    data={**body('BUY_AND_HOLD'),'firstEntry':False}
    assert evaluate(StrategyRequest.model_validate(data))['signal']=='HOLD'
    data={**body(),'direction':1}
    assert evaluate(StrategyRequest.model_validate(data))['signal']=='HOLD'


def test_execution_risk_atr_does_not_treat_a_contract_roll_gap_as_volatility():
    execution=[]
    for index,row in enumerate(rows(20)):
        price=100 if index<10 else 200
        execution.append({**row,'contract':'JM2501' if index<10 else 'JM2505',
            'open':price,'close':price,'high':price+1,'low':price-1})
    result=evaluate(StrategyRequest.model_validate({**body(bars=rows(20)),'executionBars':execution}))
    assert result['atr']==2


def test_live_context_filters_uncompleted_daily_bars_without_requiring_replay_history():
    known={'timestamp':'2026-10-19T00:00:00+08:00','open':100,'high':102,'low':99,'price':101,'volume':100}
    forming={**known,'timestamp':'2026-10-20T00:00:00+08:00','price':999}
    quote={'price':101,'dataTimestamp':'2026-10-20T10:00:00+08:00','dataStatus':'FRESH',
        'volumeMultiple':60,'priceTick':.5,'marginPerLot':1000,'commissionPerLot':3}
    feed=SimpleNamespace(provider_symbol=lambda s:'KQ.m@DCE.jm',execution_snapshot=lambda s:{
        'contract':'JM2701','marketState':'LIVE','checkedAt':'2026-10-20T10:00:00+08:00',
        'quote':quote,'history':[known,forming]},snapshot=lambda s:{'history':[known,forming]})
    result=live_context(feed,'JM0')
    assert result['contract']=='JM2701'
    assert len(result['signalBars'])==len(result['executionBars'])==1
    assert result['signalBars'][0]['close']==101
    assert result['spec']['volumeMultiple']==60
