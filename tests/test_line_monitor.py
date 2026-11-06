from datetime import datetime,timedelta,timezone
from unittest.mock import patch
from algorithm_service.line_monitor import evaluate_lines
from algorithm_service.monitor_rules import evaluate
from algorithm_service.monitor_api import Parameters

NOW=datetime(2026,11,7,1,0,3,tzinfo=timezone.utc)

def data():
    end=NOW.replace(second=0)
    minutes=[dict(timestamp=(end-timedelta(minutes=15*(600-i))).isoformat(),
                  open=100+i*.01,high=100.2+i*.01,low=99.8+i*.01,price=100+i*.01,volume=1000,openInterest=20000) for i in range(601)]
    days=[dict(timestamp=(end.replace(hour=0,minute=0)-timedelta(days=70-i)).isoformat(),
               open=100,high=101,low=99,price=100,volume=20000) for i in range(71)]
    return {'assetType':'FUTURE','depth':{'symbol':'RB2701','dataStatus':'FRESH','dataTimestamp':NOW.isoformat(),'lastPrice':106},
            'chart':{'symbol':'RB2701','dataStatus':'FRESH','dataTimestamp':NOW.isoformat(),'points':minutes},
            'daily':{'symbol':'RB2701','dataStatus':'FRESH','dataTimestamp':NOW.isoformat(),'points':days}}

def model():
    return {'version':'isolated-lines','universeCodes':['RB'],'patterns':[
        {'id':'channel','target':'LONG_ENTRY','label':'通道测试观察',
         'grade':'TENTATIVE_PROBABILITY_LIFT','path':[{'feature':'line.channelKnown','operator':'GT','threshold':.5}],
         'statistics':{'TIME':{'samples':100,'probability':.4}},'containsChan':False},
        {'id':'missing-support','target':'LONG_ENTRY','label':'无支撑不触发',
         'grade':'TENTATIVE_PROBABILITY_LIFT','path':[{'feature':'line.supportKnown','operator':'GT','threshold':.5}],
         'statistics':{'TIME':{'samples':100,'probability':.4}},'containsChan':False}]}

def test_line_alerts_store_fixed_line_evidence_without_future_labels_or_history_replay():
    with patch('algorithm_service.line_monitor.model',return_value=model()),patch('backtesting.outcome_features.targets',side_effect=AssertionError('future labels live')):
        frame=data();state,events,snapshot=evaluate_lines(frame,{},900)
        assert not events and snapshot['status']=='READY'
        state,events,snapshot=evaluate_lines(frame,{**state,'lastBar':'older'},900)
        assert len(events)==1 and events[0]['variant']=='channel'
        assert events[0]['evidence']['geometry']['lines']
        assert events[0]['evidence']['referenceWindowStart']==frame['chart']['points'][0]['timestamp']
        assert not evaluate_lines(frame,state,900)[1]
        assert not evaluate_lines(frame,{'lastBar':'older','modelVersion':'old'},900)[1]

def test_missing_stale_inactive_wrong_contract_and_delayed_frames_emit_nothing():
    with patch('algorithm_service.line_monitor.model',return_value=model()):
        previous={'lastBar':'older','modelVersion':'isolated-lines'}
        for mutate in (
            lambda f:f['depth'].update(dataStatus='CACHED'),
            lambda f:f['chart'].update(symbol='CU2701'),
            lambda f:f['chart'].update(points=f['chart']['points'][1:]),
            lambda f:f['depth'].update(dataTimestamp=(NOW+timedelta(seconds=30)).isoformat()),
            lambda f:[b.update(volume=100) for b in f['daily']['points']],
            lambda f:f['chart']['points'][-2].update(price=float('nan')),
        ):
            frame=data();mutate(frame);assert not evaluate_lines(frame,previous,900)[1]
        assert not evaluate_lines(data(),previous,900,target='EXIT')[1]

def test_shared_monitor_dispatches_lines_without_changing_default_model():
    assert Parameters().outcomeModel=='BASE'
    params=Parameters(rules=['OUTCOME_PATTERN'],outcomeModel='LINES').model_dump()
    with patch('algorithm_service.line_monitor.model',return_value=model()):
        result=evaluate(data(),{'outcome':{'lastBar':'older','modelVersion':'isolated-lines'}},params,900,NOW)
    assert result['status']=='READY' and len(result['events'])==1
    assert result['metrics']['outcome']['modelVersion']=='isolated-lines'
