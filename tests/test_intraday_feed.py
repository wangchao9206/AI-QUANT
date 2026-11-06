from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import pandas as pd
import pytest
from data.intraday_feed import IntradayFeedState, observed_bars, calendar_bars, SHANGHAI

NOW = datetime(2026, 11, 6, 2, 0, 30, tzinfo=timezone.utc)
START = NOW.replace(second=0)

def row(**changes):
    return dict(datetime=int(START.timestamp()*1e9),open=100,high=102,low=99,close=101,volume=5,close_oi=10,**changes)

class Api:
    def __init__(self): self.calls=[];self.serial=pd.DataFrame([row()]);self.fail=False
    def get_kline_serial(self,*args,**kwargs):
        self.calls.append((args,kwargs))
        if self.fail: raise RuntimeError('provider unavailable')
        return self.serial
    def is_changing(self,serial): return True

def prepared():
    state=IntradayFeedState();key=state.request('RB2701',60,{'RB2701':'SHFE.rb2701'});api=Api()
    state.subscribe_pending(api,{'RB2701':'SHFE.rb2701'})
    return state,key,api

def test_probability_context_has_600_closed_bars_plus_one_forming_bar():
    state=IntradayFeedState();providers={'RB2701':'SHFE.rb2701'}
    key=state.request('RB2701',900,providers);api=Api()
    api.serial=pd.DataFrame([{**row(),'datetime':int((START-timedelta(minutes=15*(600-i))).timestamp()*1e9)} for i in range(601)])
    state.subscribe_pending(api,providers)
    assert api.calls[0][1]['data_length']==601
    assert len(state.snapshot(key,{},False,15,limit=601)['points'])==601
    assert len(state.snapshot(key,{},False,15,limit=400)['points'])==400

def test_preserves_observed_ohlcv_and_excludes_bad_data_without_filling():
    invalid=[{**row(),**changes} for changes in ({'datetime':0},{'close':float('nan')},{'high':99},{'volume':None},{'low':103})]
    bars=observed_bars([row(),*invalid]);assert len(bars)==1
    assert bars[0]['price']==101 and bars[0]['open']==100 and bars[0]['volume']==5
    assert bars[0]['changePctKnown'] is False

def test_orders_and_deduplicates_provider_timestamps():
    later={**row(),'datetime':int((START+timedelta(minutes=1)).timestamp()*1e9),'close':102}
    bars=observed_bars([later,row(),{**later,'close':100}]);assert len(bars)==2
    assert bars[1]['price']==100 and bars[1]['changePctKnown'] is True

def test_subscribes_once_and_captures_updates_to_same_candle():
    state,key,api=prepared();state.subscribe_pending(api,{'RB2701':'SHFE.rb2701'})
    api.serial.loc[0,'close']=102;state.update(api)
    assert len(api.calls)==1 and api.calls[0][0]==('SHFE.rb2701',60)
    snap=state.snapshot(key,{'dataTimestamp':NOW.isoformat()},True,15,now=NOW)
    assert snap['points'][0]['price']==102 and snap['dataStatus']=='FRESH'
    snap['points'][0]['price']=1
    assert state.snapshot(key,{},False,15,now=NOW)['points'][0]['price']==102

@pytest.mark.parametrize('connected,stamp,status',[(False,NOW,'CACHED'),(True,NOW-timedelta(seconds=20),'CACHED'),(True,NOW+timedelta(seconds=1),'CACHED'),(True,NOW,'FRESH'),(True,NOW+timedelta(minutes=2),'CACHED')])
def test_freshness_uses_quote_time_and_matching_candle_not_retrieval_time(connected,stamp,status):
    state,key,_=prepared()
    assert state.snapshot(key,{'dataTimestamp':stamp.isoformat()},connected,15,now=NOW)['dataStatus']==status

def test_limits_requests_and_never_calls_sdk_from_request_thread():
    state=IntradayFeedState();state.MAX_SUBSCRIPTIONS=1
    state.request('RB2701',15,{'RB2701':'SHFE.rb2701'})
    state.request('RB2701',15,{'RB2701':'SHFE.rb2701'})
    with pytest.raises(ValueError): state.request('RB2701',30,{'RB2701':'SHFE.rb2701'})
    with pytest.raises(ValueError): state.request('RB2701',7,{'RB2701':'SHFE.rb2701'})
    with pytest.raises(ValueError): state.request('FAKE',60,{'RB2701':'SHFE.rb2701'})

def test_reconnect_preserves_cached_bars_and_resubscribes():
    state,key,api=prepared();state.reset_session();state.subscribe_pending(api,{'RB2701':'SHFE.rb2701'})
    assert len(api.calls)==2 and state.snapshot(key,{},False,15)['dataStatus']=='CACHED'

def test_failed_subscription_retries_with_backoff_without_fabricated_bars():
    state=IntradayFeedState();key=state.request('RB2701',60,{'RB2701':'SHFE.rb2701'});api=Api();api.fail=True
    state.subscribe_pending(api,{'RB2701':'SHFE.rb2701'});state.subscribe_pending(api,{'RB2701':'SHFE.rb2701'})
    assert len(api.calls)==1
    with pytest.raises(ValueError): state.snapshot(key,{},False,15)

def test_http_validates_period_and_reports_warming_without_daily_fallback(monkeypatch):
    from fastapi.testclient import TestClient
    from algorithm_service.app import app,prediction_service
    def read(*args): raise ValueError('正在订阅真实小周期')
    monkeypatch.setattr(prediction_service,'market_feed',SimpleNamespace(intraday_snapshot=read))
    client=TestClient(app)
    assert client.get('/api/v1/market/RB2701/intraday?seconds=7').status_code==400
    assert client.get('/api/v1/market/RB2701/intraday?limit=601').status_code==422
    response=client.get('/api/v1/market/RB2701/intraday?seconds=15')
    assert response.status_code==503 and '订阅' in response.json()['detail']


def daily(day, index, close):
    return {**row(), 'id':index, 'datetime':int(datetime.fromisoformat(day).replace(tzinfo=SHANGHAI).timestamp()*1e9),
            'open':close-1, 'high':close+2, 'low':close-2, 'close':close,'close_oi':100+index}


def test_calendar_months_use_real_boundaries_leap_days_and_observed_ohlcv():
    bars=observed_bars([daily('2024-02-28',0,100),daily('2024-02-29',1,103),daily('2024-03-01',2,101)])
    result=calendar_bars(bars,'MONTH',True)
    assert len(result)==2 and result[0]['timestamp'].startswith('2024-02-01')
    assert result[0]['open']==99 and result[0]['price']==103 and result[0]['high']==105
    assert result[0]['low']==98 and result[0]['volume']==10 and result[0]['openInterest']==101
    assert result[1]['timestamp'].startswith('2024-03-01') and result[1]['changePctKnown']


def test_calendar_weeks_cross_years_and_skip_unobserved_holiday_days():
    bars=observed_bars([daily('2024-12-27',0,100),daily('2024-12-30',1,101),daily('2025-01-02',2,102),daily('2025-01-06',3,103)])
    result=calendar_bars(bars,'WEEK',True)
    assert len(result)==3 and result[1]['timestamp'].startswith('2024-12-30')
    assert result[1]['volume']==10 and result[1]['lastTradingDate']=='2025-01-02'
    assert calendar_bars(bars,'WEEK',False)[0]['timestamp']==result[1]['timestamp']


def test_long_periods_share_one_daily_subscription_and_refresh_current_month():
    state=IntradayFeedState();providers={'RBM':'KQ.m@SHFE.rb'};api=Api()
    api.serial=pd.DataFrame([daily('2024-02-28',0,100),daily('2024-02-29',1,103),daily('2024-03-01',2,101)])
    keys=[state.request('RBM',p,providers) for p in ('DAY','WEEK','MONTH')]
    state.subscribe_pending(api,providers);state.subscribe_pending(api,providers)
    assert len(api.calls)==1 and api.calls[0]==(('KQ.m@SHFE.rb',86400),{'data_length':8000})
    api.serial.loc[2,'close']=102;state.update(api)
    snapshot=state.snapshot(keys[-1],{},False,15)
    assert snapshot['period']=='MONTH' and snapshot['seconds']==0 and snapshot['points'][-1]['price']==102
    assert state.snapshot(keys[0],{},False,15)['seconds']==86400


def test_calendar_updates_reject_missing_daily_observations_and_recover_without_reconnect():
    state=IntradayFeedState();providers={'RBM':'KQ.m@SHFE.rb'};api=Api()
    api.serial=pd.DataFrame([daily('2026-11-05',0,100),daily('2026-11-06',1,101)])
    key=state.request('RBM','MONTH',providers);state.subscribe_pending(api,providers)
    api.serial.loc[1,'close']=float('nan');state.update(api)
    snap=state.snapshot(key,{'dataTimestamp':NOW.isoformat()},True,15,now=NOW)
    assert snap['dataStatus']=='CACHED' and '校验失败' in snap['message'] and snap['points'][-1]['price']==101
    api.serial.loc[1,'close']=102;state.update(api)
    assert state.snapshot(key,{'dataTimestamp':NOW.isoformat()},True,15,now=NOW)['dataStatus']=='FRESH'


def test_long_period_freshness_compares_exchange_trading_date_including_night_session():
    state=IntradayFeedState();providers={'RBM':'KQ.m@SHFE.rb'};api=Api()
    api.serial=pd.DataFrame([daily('2026-11-09',0,100)])
    key=state.request('RBM','DAY',providers);state.subscribe_pending(api,providers)
    night=datetime(2026,11,6,21,tzinfo=SHANGHAI)
    quote={'dataTimestamp':night.isoformat(),'tradingDate':'2026-11-09'}
    assert state.snapshot(key,quote,True,15,now=night)['dataStatus']=='FRESH'
    quote['tradingDate']='2026-11-06'
    assert state.snapshot(key,quote,True,15,now=night)['dataStatus']=='CACHED'


@pytest.mark.parametrize('period',['DAY','WEEK','MONTH'])
def test_http_accepts_explicit_calendar_period_without_turning_it_into_fixed_seconds(monkeypatch,period):
    from fastapi.testclient import TestClient
    from algorithm_service.app import app,prediction_service
    calls=[]
    def read(symbol,selected,limit):calls.append((symbol,selected,limit));return {'period':selected,'points':[]}
    monkeypatch.setattr(prediction_service,'market_feed',SimpleNamespace(intraday_snapshot=read))
    client=TestClient(app)
    assert client.get('/api/v1/market/RBM/intraday?period='+period).status_code==200
    assert calls==[('RBM',period,400)]
    assert client.get('/api/v1/market/RBM/intraday?period=YEAR').status_code==400
