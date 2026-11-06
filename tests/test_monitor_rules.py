import copy
import json
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from algorithm_service.monitor_api import Parameters,router_for
from algorithm_service.monitor_rules import evaluate,technical_signals

NOW=datetime(2026,11,6,2,0,30,tzinfo=timezone.utc)
PARAMS=Parameters().model_dump()

def candles(prices,now=NOW):
    end=now.replace(second=0,microsecond=0)
    return [dict(timestamp=(end-timedelta(minutes=len(prices)-i-1)).isoformat(),open=p,high=p+1,low=p-1,price=p,volume=10) for i,p in enumerate(prices)]

def frame(now=NOW,price=100,trades=None,points=None,status='FRESH'):
    return {'depth':{'symbol':'RB2701','dataStatus':status,'dataTimestamp':now.isoformat(),'lastPrice':price,
                     'bids':[{'level':1,'price':price-1,'volume':10}],'asks':[{'level':1,'price':price,'volume':10}],'trades':trades or []},
            'chart':{'symbol':'RB2701','dataStatus':status,'dataTimestamp':now.isoformat(),'points':points or candles([100]*60,now)}}

def tick(index,now,side='BUY',lots=200):
    return {'id':str(index),'timestamp':now.isoformat(),'price':100,'volume':lots,'side':side}

@pytest.mark.parametrize('direction',[1,-1])
def test_volume_breakouts_cover_ma_and_all_three_channels(direction):
    bars=candles([100]*200+[119 if direction>0 else 81]);bars[-1]['volume']=50
    result=technical_signals(bars,60,PARAMS);codes={r['rule'] for r in result}
    suffix='UP' if direction>0 else 'DOWN'
    assert {'VOLUME_SPIKE','VOLUME_BREAKOUT_'+suffix,'MA_BREAKOUT_'+suffix,'BOLL_BREAKOUT_'+suffix,
            'DONCHIAN_'+suffix,'KELTNER_'+suffix,'ATR_MOVE'}<=codes
    assert {e['variant'] for e in result if e['rule']=='MA_BREAKOUT_'+suffix}=={'MA5','MA10','MA20','MA60','MA180'}

def test_forming_candle_does_not_trigger_technical_breakouts():
    initial=evaluate(frame(),{},PARAMS,60,NOW)
    later=NOW+timedelta(seconds=3);points=candles([100]*59+[150]);points[-1]['volume']=10000
    state=copy.deepcopy(initial['state']);state['lastBar']='older'
    result=evaluate(frame(later,150,points=points),state,PARAMS,60,later)
    assert not any(e['rule'].startswith(('MA_','BOLL_','VOLUME_','DONCHIAN_')) for e in result['events'])

@pytest.mark.parametrize('direction,code',[(1,'PRICE_UP_60S'),(-1,'PRICE_DOWN_60S')])
def test_rolling_sixty_second_returns_require_a_real_baseline_and_emit_only_on_entry(direction,code):
    params={**PARAMS,'rules':[code]};state={};found=[]
    for i in range(21):
        now=NOW+timedelta(seconds=i*3);price=100 if i<20 else 100+direction*11
        result=evaluate(frame(now,price),state,params,60,now);state=json.loads(json.dumps(result['state']))
        if i<20:assert not result['events']
        found+=result['events']
    assert [e['rule'] for e in found]==[code]
    now+=timedelta(seconds=3)
    assert not evaluate(frame(now,price),state,params,60,now)['events']
    assert found[0]['evidence']['windowSeconds']==60

def test_irregular_sampling_does_not_count_a_price_outside_the_last_minute():
    state={}
    for elapsed in [*range(0,61,4),61]:
        now=NOW+timedelta(seconds=elapsed)
        price=100 if elapsed==0 else 105 if elapsed<61 else 111
        result=evaluate(frame(now,price),state,{**PARAMS,'rules':['PRICE_UP_60S']},60,now)
        state=result['state']
    assert result['metrics']['windowReady']
    assert result['metrics']['change60sPct']==pytest.approx(100*6/105)
    assert not result['events']  # The 11% move started 61 seconds ago.


def test_gaps_restart_the_window_and_cached_future_or_zero_prices_never_trigger():
    state=evaluate(frame(),{},PARAMS,60,NOW)['state']
    for data in [frame(status='CACHED'),frame(NOW+timedelta(seconds=1)),frame(price=0)]:
        result=evaluate(data,state,PARAMS,60,NOW);assert not result['events'] and result['status']=='STALE'
    later=NOW+timedelta(seconds=30)
    result=evaluate(frame(later,150),state,PARAMS,60,later)
    assert result['status']=='WARMING' and not result['events'] and len(result['state']['samples'])==1


@pytest.mark.parametrize('price',[110,90])
def test_exact_ten_percent_does_not_mean_more_than_ten_percent(price):
    state={}
    for i in range(21):
        now=NOW+timedelta(seconds=3*i)
        result=evaluate(frame(now,100 if i<20 else price),state,{**PARAMS,'rules':['PRICE_UP_60S','PRICE_DOWN_60S']},60,now)
        state=result['state']
    assert not result['events']

def test_large_tick_increments_are_deduplicated_and_keep_estimated_direction():
    state=evaluate(frame(trades=[tick(1,NOW)]),{},PARAMS,60,NOW)['state']
    now=NOW+timedelta(seconds=3);result=evaluate(frame(now,trades=[tick(2,now),tick(1,NOW)]),state,PARAMS,60,now)
    assert [e['rule'] for e in result['events']]==['BIG_BUY']
    assert result['events'][0]['evidence']['directionBasis']=='TICK_PRICE_VS_BID_ASK_ESTIMATE'
    state=result['state'];assert not evaluate(frame(now,trades=[tick(2,now)]),state,PARAMS,60,now)['events']
    now+=timedelta(seconds=3);result=evaluate(frame(now,trades=[tick(3,now,'SELL'),tick(4,now,'NEUTRAL')]),state,PARAMS,60,now)
    assert {e['rule'] for e in result['events']}=={'BIG_SELL','BIG_NEUTRAL'}

@pytest.mark.parametrize('rule,direction',[('MACD_GOLDEN',1),('MACD_DEAD',-1)])
def test_macd_crosses_use_real_dif_and_dea(rule,direction):
    prices=[100-direction*i*.4 for i in range(40)]+[84 if direction==1 else 116]
    prices += [prices[-1]+direction*i*.8 for i in range(1,25)]
    found=[e for length in range(35,len(prices)+1) for e in technical_signals(candles(prices[:length]),60,PARAMS) if e['rule']==rule]
    assert found and all('dif' in e['evidence'] and 'dea' in e['evidence'] for e in found)

@pytest.mark.parametrize('bottom',[True,False])
def test_divergence_waits_for_two_later_closed_candles_and_records_both_pivots(monkeypatch,bottom):
    bars=candles([100]*50);key='low' if bottom else 'high';bars[35][key]=90 if bottom else 110;bars[45][key]=89 if bottom else 111
    def oscillator(closes):
        dif=[-2 if bottom else 2 for _ in closes]
        if len(dif)>35:dif[35]=-3 if bottom else 3
        if len(dif)>45:dif[45]=-1 if bottom else 1
        return dif,list(dif)
    monkeypatch.setattr('algorithm_service.monitor_rules.macd',oscillator)
    code='MACD_BOTTOM' if bottom else 'MACD_TOP'
    assert not any(e['rule']==code for e in technical_signals(bars[:47],60,PARAMS))
    events=[e for e in technical_signals(bars[:48],60,PARAMS) if e['rule']==code]
    assert len(events)==1 and events[0]['evidence']['secondPivot']==bars[45]['timestamp']
    assert events[0]['evidence']['confirmationBar']==bars[47]['timestamp'] and events[0]['evidence']['rightClosedBars']==2

def test_cooldowns_apply_to_technical_rules_and_missing_history_is_not_filled():
    assert technical_signals(candles([100]*3),60,PARAMS)==[]
    now=NOW+timedelta(seconds=3);points=candles([100]*59+[120,120]);points[-2]['volume']=100
    state=evaluate(frame(),{},PARAMS,60,NOW)['state'];state['lastBar']='older';state['cooldowns']['VOLUME_SPIKE:']=now.timestamp()-1
    result=evaluate(frame(now,120,points=points),state,{**PARAMS,'rules':['VOLUME_SPIKE']},60,now)
    assert not result['events']

def test_internal_monitor_endpoints_require_secret_and_validate_configuration(monkeypatch):
    secret='test-monitor-service-secret-at-least-32-characters';monkeypatch.setenv('IDENTITY_INTERNAL_SECRET',secret)
    app=FastAPI();app.include_router(router_for(SimpleNamespace()));client=TestClient(app)
    assert client.get('/internal/v1/monitor/catalog').status_code==403
    headers={'X-Identity-Service-Secret':secret};assert client.get('/internal/v1/monitor/catalog',headers=headers).status_code==200
    body={'assetType':'FUTURE','symbol':'RB2701','seconds':7,'parameters':{}}
    assert client.post('/internal/v1/monitor/validate',headers=headers,json=body).status_code==422
    body['seconds']=60;body['parameters']={'rules':['forged']}
    assert client.post('/internal/v1/monitor/validate',headers=headers,json=body).status_code==422

def test_corrupt_bars_suspend_monitoring_instead_of_omitting_bad_observations():
    data=frame();data['chart']['points'][20]['high']=1
    result=evaluate(data,{},PARAMS,60,NOW)
    assert result['status']=='ERROR' and not result['events']


def test_history_metrics_exclude_forming_bar_and_preserve_missing_windows():
    points=candles([100]*200+[999]);points[-1]['volume']=999999
    result=evaluate(frame(price=100,points=points),{},PARAMS,60,NOW)
    metrics=result['metrics']
    assert metrics['ma180']==100 and metrics['volume']==10
    assert metrics['volumeRatio']==1 and metrics['dif']==0 and metrics['dea']==0
    assert metrics['bollUpper']==100 and metrics['atr']==2
    short=evaluate(frame(points=candles([100]*3)),{},PARAMS,60,NOW)['metrics']
    assert short['ma5'] is None and short['dif'] is None and short['volumeRatio'] is None


def test_stale_history_has_no_recycled_price_or_indicators():
    result=evaluate(frame(status='CACHED'),{},PARAMS,60,NOW)
    assert result['status']=='STALE'
    assert 'lastPrice' not in result['metrics'] and 'ma20' not in result['metrics']
