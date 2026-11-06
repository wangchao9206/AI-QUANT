from datetime import datetime,timedelta,timezone
import csv,gzip,json
from pathlib import Path
from backtesting.trend_features import features
from algorithm_service.research_context import evaluate_context,alert_assessment

ROOT=Path(__file__).resolve().parents[1]
def daily(day=0):
    start=datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(days=day)
    return {'points':[{'timestamp':(start+timedelta(days=i)).isoformat(),'open':100+i,'price':100+i,'high':101+i,'low':99+i,'volume':100} for i in range(31)]}

def test_features_are_causal_scale_invariant_and_require_real_windows():
    bars=daily()['points'][:-1];value=features(bars)
    assert value['regime']=='UP' and 'UP_TREND' in value['conditions']
    scaled=[{**b,**{k:b[k]*10 for k in ('price','open','high','low')}} for b in bars]
    assert features(scaled)['conditions']==value['conditions']
    assert features(bars[:24]) is None
    assert features([{**b,'volume':-1} for b in bars]) is None

def test_pivots_are_reported_only_after_two_right_hand_complete_bars():
    bars=daily()['points'][:-1];bars[-3]['low']=1
    assert 'LOW_PIVOT' not in features(bars[:-1])['conditions']
    assert 'LOW_PIVOT' in features(bars)['conditions']

def test_daily_research_queues_across_reconnect_once_and_never_promotes_failed_results():
    state,events,context=evaluate_context(daily(),{},True,False)
    assert not events and context['qualification']=='EXPLORATORY_NOT_LIVE_QUALIFIED'
    state,events,_=evaluate_context(daily(1),state,True,False)
    assert not events and state['pending']
    state,events,_=evaluate_context(daily(1),state,True,True)
    assert events and all(e['evidence']['historicallyConsistent'] is False for e in events)
    assert not evaluate_context(daily(1),state,True,True)[1]
    stale,events,_=evaluate_context(None,state,False,False)
    assert stale['reference']==state['reference'] and not events

def test_archived_events_do_not_cross_time_splits_or_overlap_in_a_condition_account():
    file=ROOT/'docs/research/data/trend-opportunities-2026-11-07/events.csv.gz'
    previous={};count=0
    with gzip.open(file,'rt',encoding='utf-8',newline='') as stream:
        for row in csv.DictReader(stream):
            key=(row['symbol'],row['condition'],row['horizon'],row['stage'])
            assert row['signalDate']<row['entryDate']<=row['exitDate']
            assert previous.get(key,'0000')<row['signalDate']
            assert float(row['netPct'])<=float(row['grossPct'])
            assert float(row['costPct'])>=0
            if row['stage']=='DEVELOPMENT':assert row['exitDate']<'2023-01-01'
            elif row['stage']=='VALIDATION':assert '2023-01-01'<=row['signalDate']<=row['exitDate']<'2025-01-01'
            else:assert row['signalDate']>='2025-01-01'
            previous[key]=row['exitDate'];count+=1
    report=json.loads((file.parent/'results.json').read_text(encoding='utf-8'))
    assert count==report['eventOutcomes']

def test_tick_touch_and_custom_periods_never_inherit_fifteen_minute_statistics():
    assert alert_assessment('DAILY_MA_PULLBACK',5,900)['qualification']=='NOT_VALIDATED_FOR_THIS_RULE'
    assert alert_assessment('DAILY_MA_BREAKOUT_UP',20,60)['qualification']=='NOT_VALIDATED_FOR_THIS_RULE'
    actual=alert_assessment('DAILY_MA_BREAKOUT_UP',20,900)
    assert actual['condition']=='CROSS_DAY20_UP' and actual['tradeQualified'] is False
    assert actual['selected']['VALIDATION']['samples']==97

def test_intraday_labels_use_only_completed_daily_references_and_respect_splits():
    file=ROOT/'docs/research/data/intraday-alert-validation-2026-11-07/events.json.gz'
    with gzip.open(file,'rt',encoding='utf-8') as stream:rows=json.load(stream)
    previous={}
    for row in rows:
        assert row['dailyReferenceAt']<row['formingDayAt']<=row['signalAt']<row['confirmedAt']
        assert row['entryAt']==row['confirmedAt']<=row['exitBarAt']
        key=(row['contract'],row['condition'],row['horizon'],row['phase'])
        assert previous.get(key,'0000')<row['signalAt'];previous[key]=row['exitBarAt']
        assert row['netPct']<=row['grossPct']
    report=json.loads((file.parent/'results.json').read_text(encoding='utf-8'))
    assert len(rows)==report['eventOutcomes']
    assert report['source15mBars']-report['usable15mBars']==3609
