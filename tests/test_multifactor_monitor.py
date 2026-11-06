from datetime import datetime,timedelta,timezone
from unittest.mock import patch
from algorithm_service.multifactor_monitor import evaluate_multifactor
from algorithm_service.monitor_rules import evaluate
from algorithm_service.monitor_api import Parameters

NOW=datetime(2026,11,7,1,0,3,tzinfo=timezone.utc)

def data():
    end=NOW.replace(second=0)
    minutes=[dict(timestamp=(end-timedelta(minutes=15*(600-i))).isoformat(),
                  open=100,high=100.2,low=99.8,price=100,volume=1000,openInterest=20000) for i in range(601)]
    days=[dict(timestamp=(end.replace(hour=0,minute=0)-timedelta(days=70-i)).isoformat(),
               open=100,high=101,low=99,price=100,volume=20000) for i in range(71)]
    return {'assetType':'FUTURE','depth':{'symbol':'RB2701','dataStatus':'FRESH','dataTimestamp':NOW.isoformat(),'lastPrice':100},
            'chart':{'symbol':'RB2701','dataStatus':'FRESH','dataTimestamp':NOW.isoformat(),'points':minutes},
            'daily':{'symbol':'RB2701','dataStatus':'FRESH','dataTimestamp':NOW.isoformat(),'points':days}}

def model():
    return {'version':'isolated-multi','universeCodes':['RB'],'patterns':[{
        'id':'isolated','family':'COMBINED','target':'LONG_ENTRY','label':'测试观察',
        'grade':'TENTATIVE_PROBABILITY_LIFT','path':[{'feature':'m15.rsi14','operator':'LE','threshold':100}],
        'containsChan':False,'statistics':{'TIME':{'samples':100,'probability':.4}}}]}

def test_new_model_has_no_startup_replay_duplicates_or_future_label_calls():
    frame=data()
    with patch('algorithm_service.multifactor_monitor.model',return_value=model()),patch('backtesting.outcome_features.targets',side_effect=AssertionError('future labels live')):
        state,events,snapshot=evaluate_multifactor(frame,{},900)
        assert not events and snapshot['status']=='READY'
        older={**state,'lastBar':'older'}
        state,events,snapshot=evaluate_multifactor(frame,older,900)
        assert len(events)==1 and events[0]['evidence']['contextBars']['m60']>=60
        assert events[0]['evidence']['tradeQualified'] is False
        assert not evaluate_multifactor(frame,state,900)[1]
        assert not evaluate_multifactor(frame,{'lastBar':'older','modelVersion':'previous-model'},900)[1]

def test_stale_short_inactive_and_late_frames_emit_nothing():
    with patch('algorithm_service.multifactor_monitor.model',return_value=model()):
        previous={'lastBar':'older','modelVersion':'isolated-multi'}
        for mutate in (
            lambda f:f['depth'].update(dataStatus='CACHED'),
            lambda f:f['daily'].update(dataStatus='CACHED'),
            lambda f:f['chart'].update(points=f['chart']['points'][1:]),
            lambda f:f['depth'].update(dataTimestamp=(NOW+timedelta(seconds=30)).isoformat()),
            lambda f:[b.update(volume=100) for b in f['daily']['points']],
        ):
            frame=data();mutate(frame);assert not evaluate_multifactor(frame,previous,900)[1]
        assert not evaluate_multifactor(data(),previous,900,family='CHAN_ONLY')[1]
        assert not evaluate_multifactor(data(),previous,900,target='EXIT')[1]

def test_shared_monitor_dispatches_extended_model_and_keeps_baseline_version_isolated():
    params=Parameters(rules=['OUTCOME_PATTERN'],outcomeModel='MULTI').model_dump()
    with patch('algorithm_service.multifactor_monitor.model',return_value=model()):
        result=evaluate(data(),{'outcome':{'lastBar':'older','modelVersion':'isolated-multi'}},params,900,NOW)
    assert result['status']=='READY' and result['events']
    assert result['metrics']['outcome']['modelVersion']=='isolated-multi'
