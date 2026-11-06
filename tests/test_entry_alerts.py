from datetime import datetime,timedelta,timezone
from algorithm_service.entry_alerts import evaluate_entry_alerts

NOW=datetime(2026,11,7,2,0,3,tzinfo=timezone.utc)
def fixtures(period=20):
    daily={'dataStatus':'FRESH','dataTimestamp':NOW.isoformat(),'points':[
        {'timestamp':(NOW.replace(hour=0,minute=0,second=0)-timedelta(days=period-i)).isoformat(),'price':100}
        for i in range(period+1)]}
    daily['points'][-1]['price']=999  # The unfinished day must never enter the reference.
    closed=[{'timestamp':(NOW-timedelta(seconds=123)).isoformat(),'price':99},
            {'timestamp':(NOW-timedelta(seconds=63)).isoformat(),'price':101}]
    depth={'lastPrice':101,'dataTimestamp':NOW.isoformat()}
    return daily,closed,depth

def test_crosses_daily_ma_only_on_a_new_closed_intraday_bar_without_volume_requirement():
    daily,closed,depth=fixtures()
    state,events,metrics=evaluate_entry_alerts(daily,closed,depth,{},20,.2,60)
    assert not events and metrics['dailyMA']==100
    old={**state,'lastBar':'older'}
    state,events,_=evaluate_entry_alerts(daily,closed,depth,old,20,.2,60)
    assert [e['rule'] for e in events]==['DAILY_MA_BREAKOUT_UP']
    assert events[0]['evidence']['confirmation']=='BAR_CLOSE'
    assert events[0]['evidence']['referencePeriod']=='DAY'
    assert not evaluate_entry_alerts(daily,closed,depth,state,20,.2,60)[1]

def test_pullback_is_an_observed_approach_from_above_not_a_replayed_daily_low():
    daily,closed,depth=fixtures(5)
    for b in daily['points'][:-1]:b['price']=99.5
    daily['points'][-2]['price']=102
    depth['lastPrice']=102
    state,events,_=evaluate_entry_alerts(daily,closed,depth,{},5,.2,60)
    assert not events
    depth['lastPrice']=100.1
    state,events,_=evaluate_entry_alerts(daily,closed,depth,state,5,.2,60)
    assert [e['rule'] for e in events]==['DAILY_MA_PULLBACK']
    assert events[0]['evidence']['confirmation']=='INTRABAR_TOUCH'
    assert not evaluate_entry_alerts(daily,closed,depth,state,5,.2,60)[1]

def test_missing_stale_future_or_insufficient_daily_evidence_never_triggers():
    daily,closed,depth=fixtures();daily['dataStatus']='CACHED'
    assert not evaluate_entry_alerts(daily,closed,depth,{},20,.2,60)[1]
    daily['dataStatus']='FRESH';daily['points'][-1]['timestamp']=(NOW+timedelta(days=1)).isoformat()
    assert evaluate_entry_alerts(daily,closed,depth,{},20,.2,60)[2]['dailyMA'] is None
    assert evaluate_entry_alerts(None,closed,depth,{},20,.2,60)[2]['dailyMA'] is None

def test_downward_cross_and_reference_rollover_are_separate_from_old_signals():
    daily,closed,depth=fixtures();closed[-2]['price']=101;closed[-1]['price']=99
    state,_,_=evaluate_entry_alerts(daily,closed,depth,{},20,.2,60)
    _,events,_=evaluate_entry_alerts(daily,closed,depth,{**state,'lastBar':'older'},20,.2,60)
    assert events[0]['rule']=='DAILY_MA_BREAKOUT_DOWN'
    assert not evaluate_entry_alerts(daily,closed,depth,{**state,'reference':'yesterday'},20,.2,60)[1]

def test_full_monitor_wires_daily_reference_and_suppresses_a_forming_bar_breakout():
    from algorithm_service.monitor_api import Parameters
    from algorithm_service.monitor_rules import evaluate
    daily,closed,depth=fixtures()
    for bar in closed:bar.update(open=bar['price'],high=bar['price']+1,low=bar['price']-1,volume=10)
    forming={'timestamp':NOW.isoformat(),'price':150,'open':101,'high':151,'low':100,'volume':9999}
    data={'daily':daily,'depth':{**depth,'dataStatus':'FRESH','bids':[],'asks':[]},'chart':{'dataStatus':'FRESH','dataTimestamp':NOW.isoformat(),'points':closed+[forming]}}
    params=Parameters(rules=['DAILY_MA_BREAKOUT_UP']).model_dump()
    first=evaluate(data,{},params,60,NOW)
    assert first['metrics']['dailyMA']==100 and not first['events']
    # Same completed bar: a large move in the provisional last bar is not a confirmed crossing.
    second=evaluate(data,first['state'],params,60,NOW)
    assert not second['events'] and second['status']=='READY'
    data['daily']=None
    pending=evaluate(data,second['state'],params,60,NOW)
    assert pending['status']=='WARMING' and not pending['events']
