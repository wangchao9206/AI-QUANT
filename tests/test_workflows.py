"""Synthetic, isolated verification of causal workflow rules and real ledgers."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import pytest
from backtesting.workflow import compile_workflow,PRESETS
from backtesting.backtester import QuantitativeBacktester
from data.data_feed import KLineBar
from data.tqsdk_backtest import FuturesContractSpec
from algorithm_service.paper_strategy import StrategyRequest,evaluate


def graph(preset=None):
    nodes=[{'id':'market','type':'MARKET'},{'id':'risk','type':'RISK','params':{'lots':2,'stopLossAtr':2,'takeProfitAtr':3}},
           {'id':'buy','type':'ACTION','params':{'action':'BUY'}}]
    edges=[{'id':'risk-buy','source':'risk','sourcePort':'risk','target':'buy','targetPort':'risk'}]
    if preset:
        nodes.extend([{'id':'core','type':'PRESET','params':{'strategy':preset}},
                      {'id':'sell','type':'ACTION','params':{'action':'SELL'}},{'id':'close','type':'ACTION','params':{'action':'FLATTEN'}}])
        edges.append({'id':'market-core','source':'market','sourcePort':'bars','target':'core','targetPort':'market'})
        for action,port in [('buy','buy'),('sell','sell'),('close','close')]:
            edges.append({'id':'signal-'+action,'source':'core','sourcePort':port,'target':action,'targetPort':'condition'})
            if action!='buy':edges.append({'id':'risk-'+action,'source':'risk','sourcePort':'risk','target':action,'targetPort':'risk'})
    else:
        nodes.extend([{'id':'price','type':'PRICE'},{'id':'zero','type':'CONSTANT'}, {'id':'condition','type':'COMPARE'}])
        for source,source_port,target,target_port in [('market','bars','price','market'),('price','value','condition','left'),('zero','value','condition','right'),('condition','result','buy','condition')]:
            edges.append({'id':source+'-'+target,'source':source,'sourcePort':source_port,'target':target,'targetPort':target_port})
    return {'schemaVersion':1,'nodes':nodes,'edges':edges}


def bars(count=80):
    return [KLineBar(datetime(2025,1,1,tzinfo=timezone.utc)+timedelta(days=i),100+i*.1,101+i*.1,99+i*.1,100+i*.1,10000,10000,'JM2701') for i in range(count)]


@pytest.mark.parametrize('preset',sorted(PRESETS))
def test_existing_preset_nodes_are_executable_and_report_warmup(preset):
    program=compile_workflow(graph(preset));result=program.prepare(bars()).evaluate(70)
    assert result.signal in ('BUY','SELL','FLATTEN','HOLD')
    assert len(result.node_trace)==6
    assert program.prepare(bars(1)).evaluate(0).signal=='WARMING'


def test_future_bars_do_not_change_an_earlier_decision_or_indicator():
    definition=graph();definition['nodes'][3]={'id':'price','type':'INDICATOR','params':{'kind':'EMA','period':5,'shift':1}}
    original=bars();changed=deepcopy(original)
    for row in changed[31:]:row.close=999999
    a=compile_workflow(definition).prepare(original).evaluate(30)
    b=compile_workflow(definition).prepare(changed).evaluate(30)
    assert a==b
    assert next(row for row in a.node_trace if row['type']=='MARKET')['value']['bars']==31


def test_rejects_future_offsets_wrong_ports_cycles_and_unused_nodes():
    future=graph();future['nodes'][3]['params']={'shift':-1}
    with pytest.raises(ValueError,match='历史偏移'):compile_workflow(future)
    wrong=graph();wrong['edges'][-1]['source']='market';wrong['edges'][-1]['sourcePort']='bars'
    with pytest.raises(ValueError,match='类型不符'):compile_workflow(wrong)
    cycle=graph();cycle['nodes'].append({'id':'loop','type':'LOGIC','params':{'op':'AND'}})
    cycle['edges'][-1]={'id':'loop-buy','source':'loop','sourcePort':'result','target':'buy','targetPort':'condition'}
    cycle['edges'].extend([{'id':'loop-self','source':'loop','sourcePort':'result','target':'loop','targetPort':'a'},
        {'id':'condition-loop','source':'condition','sourcePort':'result','target':'loop','targetPort':'b'}])
    with pytest.raises(ValueError,match='循环'):compile_workflow(cycle)
    unused=graph();unused['nodes'].append({'id':'unused','type':'CONSTANT'})
    with pytest.raises(ValueError,match='未连接'):compile_workflow(unused)


def test_conflicting_long_and_short_candidates_wait_instead_of_picking_one():
    definition=graph();definition['nodes'].append({'id':'sell','type':'ACTION','params':{'action':'SELL'}})
    definition['edges'].extend([{'id':'condition-sell','source':'condition','sourcePort':'result','target':'sell','targetPort':'condition'},
        {'id':'risk-sell','source':'risk','sourcePort':'risk','target':'sell','targetPort':'risk'}])
    result=compile_workflow(definition).prepare(bars()).evaluate(10)
    assert result.signal=='HOLD' and '同时' in result.reason


def test_paper_evaluation_excludes_future_rows_and_emits_node_trace():
    observed=bars()
    rows=[{'timestamp':b.timestamp,'contract':b.contract_symbol,'open':b.open,'high':b.high,'low':b.low,'close':b.close,'volume':b.volume} for b in observed]
    request=StrategyRequest(strategy='WORKFLOW',symbol='JM0',asOf=observed[30].timestamp,bars=rows,executionBars=rows,workflow=graph())
    result=evaluate(request)
    assert result['historyCount']==31 and result['modelVersion']=='workflow-daily-v1'
    assert result['signal']=='BUY' and len(result['nodeTrace'])==6


def test_workflow_backtest_uses_fixed_lots_and_stops_before_take_profit_on_ambiguous_bar():
    observed=bars(40);observed[1]=KLineBar(observed[1].timestamp,100,120,80,100,10000,10000,'JM2701')
    result=QuantitativeBacktester().run_backtest(observed,strategy='WORKFLOW',symbol='JM0',workflow=graph(),slippage=0,fee_rate=0,
        contract_specs={'JM2701':FuturesContractSpec('JM2701',60,.5,1000,0)})
    entries=[t for t in result.trade_logs if t.action in ('OPEN_BUY','OPEN_SHORT')]
    assert entries and all(t.lots==2 for t in entries)
    assert entries[0].timestamp==observed[1].timestamp
    first_close=next(t for t in result.trade_logs if t.action=='FLATTEN_LONG')
    assert first_close.timestamp==observed[1].timestamp and '止损' in first_close.reason


def test_rejects_arbitrary_operations_and_missing_risk():
    definition=graph();definition['nodes'][5]['params']={'op':'__import__'}
    with pytest.raises(ValueError,match='运算无效'):compile_workflow(definition)
    definition=graph();definition['nodes'][1]['params']['lots']=0
    with pytest.raises(ValueError,match='开仓手数'):compile_workflow(definition)

def test_signal_debug_uses_only_completed_observed_bars_and_never_falls_back():
    from types import SimpleNamespace
    from fastapi import HTTPException
    from algorithm_service.workflows import DebugRequest,debug
    observed=bars(70)
    as_of=observed[30].timestamp+timedelta(hours=1)
    request=DebugRequest(definition=graph(),symbol='JM0',asOf=as_of)
    provider=SimpleNamespace(cached_replay=lambda symbol:SimpleNamespace(bars=observed,signal_bars=observed,source='ISOLATED_TEST_FIXTURE'))
    result=debug(request,provider,'JMM')
    assert result['historyCount']==30
    assert result['executionMode']=='SIGNAL_ONLY'
    assert result['source']=='ISOLATED_TEST_FIXTURE'
    assert result['nodeTrace']
    provider.cached_replay=lambda symbol:None
    with pytest.raises(HTTPException) as error:debug(request,provider,'JMM')
    assert error.value.status_code==503


def test_workflow_request_canonicalizes_graph_and_cannot_override_risk():
    from algorithm_service.models import BacktestRequest
    request=BacktestRequest(symbol='JM0',strategy='WORKFLOW',workflowDefinition=graph(),stopLossAtr=19,takeProfitAtr=49)
    assert request.stop_loss_atr==2 and request.take_profit_atr==3
    with pytest.raises(ValueError):BacktestRequest(symbol='JM0',strategy='WORKFLOW')
    with pytest.raises(ValueError):BacktestRequest(symbol='JM0',strategy='BUY_AND_HOLD',workflowDefinition=graph())
