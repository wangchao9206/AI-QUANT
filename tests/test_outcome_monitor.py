from datetime import datetime,timedelta,timezone
from unittest.mock import patch
import pytest
from algorithm_service.monitor_api import Parameters,Spec
from algorithm_service.outcome_monitor import evaluate_outcome
from algorithm_service.monitor_rules import evaluate
from backtesting.outcome_features import vector,targets

NOW=datetime(2026,11,7,1,0,3,tzinfo=timezone.utc)
def data():
    end=NOW.replace(second=0)
    minutes=[dict(timestamp=(end-timedelta(minutes=15*(120-i))).isoformat(),open=100,high=100.1,low=99.9,price=100,volume=1000,openInterest=10000) for i in range(121)]
    days=[dict(timestamp=(end.replace(hour=0,minute=0)-timedelta(days=30-i)).isoformat(),open=120-i,high=121-i,low=119-i,price=120-i,volume=20000) for i in range(31)]
    return {'assetType':'FUTURE','depth':{'symbol':'RB2701','dataStatus':'FRESH','dataTimestamp':NOW.isoformat(),'lastPrice':100,'bids':[],'asks':[]},
        'chart':{'symbol':'RB2701','dataStatus':'FRESH','dataTimestamp':NOW.isoformat(),'points':minutes},
        'daily':{'symbol':'RB2701','dataStatus':'FRESH','dataTimestamp':NOW.isoformat(),'points':days}}

def test_live_matching_never_calls_future_labeler_and_emits_once_per_confirmed_bar():
    frame=data();previous={'lastBar':frame['chart']['points'][-3]['timestamp']}
    with patch('backtesting.outcome_features.targets',side_effect=AssertionError('Future labels cannot be evaluated live')):
        state,events,snapshot=evaluate_outcome(frame,previous,900,'ENTRY')
    assert snapshot['status']=='READY' and events
    assert all(e['evidence']['targetDefinition'] in ('LONG_ENTRY','SHORT_ENTRY') for e in events)
    assert all(e['evidence']['tradeQualified'] is False for e in events)
    assert not evaluate_outcome(frame,state,900,'ENTRY')[1]
    assert not evaluate_outcome(frame,{},900)[1]  # No history replay at creation.

def test_scope_staleness_activity_and_delayed_recovery_never_invent_alerts():
    frame=data();previous={'lastBar':'older'}
    assert evaluate_outcome(frame,previous,60)[2]['status']=='OUT_OF_SCOPE'
    frame['daily']['dataStatus']='CACHED';assert not evaluate_outcome(frame,previous,900)[1]
    frame=data();frame['depth']['dataTimestamp']=(NOW+timedelta(seconds=30)).isoformat();frame['daily']['dataTimestamp']=frame['depth']['dataTimestamp']
    assert not evaluate_outcome(frame,previous,900)[1]
    frame=data()
    for b in frame['daily']['points']:b['volume']=100
    assert evaluate_outcome(frame,previous,900)[2]['status']=='OUT_OF_ACTIVITY_SCOPE'
    with pytest.raises(ValueError):Spec(assetType='FUTURE',symbol='RB2701',seconds=60,parameters={'rules':['OUTCOME_PATTERN']})

def test_full_monitor_uses_past_features_and_preserves_outcome_watermark():
    frame=data();params=Parameters(rules=['OUTCOME_PATTERN'],outcomeTarget='ENTRY').model_dump()
    result=evaluate(frame,{'outcome':{'lastBar':'older'}},params,900,NOW)
    assert result['status']=='READY' and result['events']
    assert result['metrics']['outcome']['modelVersion']=='outcome-first-v1'
    assert not evaluate(frame,result['state'],params,900,NOW)['events']

def test_reverse_labels_are_separate_from_features_and_conservative_on_ambiguous_bar():
    frame=data();minutes=frame['chart']['points'][:-1];days=frame['daily']['points'][:-1]
    before=vector(minutes,days)
    future=[{'open':100,'high':105,'low':98,'price':104,'volume':1000} for _ in range(16)]
    outcome=targets(minutes[-1],minutes[:-1],future,1,.1)
    assert outcome['labels']['LONG_ENTRY']==0  # Both stop and target touched: stop first.
    assert vector(minutes,days)==before
