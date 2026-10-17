from copy import deepcopy
from datetime import date, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from algorithm_service.research import PlanRequest, evidence_modes, risk_scenario
from data.live_feed import SHANGHAI
from data.tqsdk_feed import TqSdkRealtimeFeed, quote_to_snapshot


def context(signal='BUY', state='LIVE', coverage=1):
    return {'symbol':'CJM','modelVersion':'test','atr':2,
        'modes':{name:{'signal':signal,'empiricalCoverage':coverage} for name in ['EMPIRICAL','CULTURAL_COMPARE']},
        'execution':{'contract':'CJ701','marketState':state,'quote':{'price':100,'volumeMultiple':10,
            'priceTick':1,'marginPerLot':100,'commissionPerLot':0,'dataTimestamp':'2026-10-19T10:00:00+08:00',
            'upperLimit':110,'lowerLimit':90}}}


def test_risk_lots_include_round_trip_costs_and_all_three_caps():
    req=PlanRequest(symbol='CJM',equity=10_000,risk_pct=1,stop_price=95,margin_rate=.1)
    plan=risk_scenario(context(),req)
    assert plan['riskPerLot']==pytest.approx(70.2)
    assert plan['maxLots']==plan['newLots']==1
    assert plan['plannedLoss']<=plan['riskBudget']
    assert plan['marginRequired']<=3000
    assert plan['notionalLeverage']<=2


@pytest.mark.parametrize('signal,side,lots,action',[
    ('HOLD','FLAT',0,'WAIT'),('HOLD','LONG',1,'HOLD_POSITION'),
    ('HOLD','LONG',5,'REDUCE'),('BUY','SHORT',1,'REVIEW_EXIT'),
])
def test_hold_is_position_aware_and_never_creates_new_lots(signal,side,lots,action):
    req=PlanRequest(symbol='CJM',equity=10_000,position_side=side,existing_lots=lots,margin_rate=.1)
    plan=risk_scenario(context(signal),req)
    assert plan['action']==action
    assert plan['newLots']==0


@pytest.mark.parametrize('state',['CLOSED_CACHE','STALE','DISCONNECTED','UNKNOWN','WARMING'])
def test_non_live_market_only_allows_preparation(state):
    plan=risk_scenario(context(state=state),PlanRequest(symbol='CJM'))
    assert plan['newLots']==0 and plan['action']=='PREPARE'
    assert plan['gates']


def test_daily_and_aggregate_risk_limits_block_new_exposure():
    for params in [{'daily_loss':20_000},{'other_risk':30_000},{'other_margin':300_000},{'other_notional':2_000_000}]:
        plan=risk_scenario(context(),PlanRequest(symbol='CJM',**params))
        assert plan['maxLots']==0 and plan['newLots']==0


def test_low_coverage_and_missing_contract_spec_do_not_invent_executable_signal():
    plan=risk_scenario(context(coverage=.5),PlanRequest(symbol='CJM'))
    assert plan['newLots']==0 and plan['action']=='PREPARE'
    c=context();c['execution']['quote']['commissionPerLot']=None
    with pytest.raises(HTTPException) as exc:risk_scenario(c,PlanRequest(symbol='CJM'))
    assert exc.value.status_code==503


def test_roll_while_planning_requires_refresh():
    with pytest.raises(HTTPException) as exc:
        risk_scenario(context(),PlanRequest(symbol='CJM',expected_contract='CJ609'))
    assert exc.value.status_code==409


@pytest.mark.parametrize('side,signal,stop',[('LONG','BUY',105),('SHORT','SELL',95)])
def test_invalid_stop_direction_is_rejected(side,signal,stop):
    with pytest.raises(HTTPException) as exc:
        risk_scenario(context(signal),PlanRequest(symbol='CJM',stop_price=stop,position_side=side,existing_lots=1))
    assert exc.value.status_code==422


def test_account_and_position_inputs_are_validated():
    for value in [0,-1,float('nan'),float('inf')]:
        with pytest.raises(ValidationError):PlanRequest(symbol='CJM',equity=value)
    with pytest.raises(HTTPException):risk_scenario(context(),PlanRequest(symbol='CJM',existing_lots=1))


def test_empirical_mode_excludes_culture_and_exposes_normalized_culture_share():
    def row(score,weight):return {'name':'test','weight':weight,'score':score,'confidence':.8,'direction':'BULLISH','included_in_score':True}
    raw={'dimensions':[row(-30,.55),{**row(None,.36),'included_in_score':False}],
         'cultural_references':[row(100,.09)]}
    modes=evidence_modes(raw)
    assert modes['EMPIRICAL']['score']==-30
    assert modes['EMPIRICAL']['culturalEffectiveWeight']==0
    assert modes['CULTURAL_COMPARE']['culturalEffectiveWeight']==pytest.approx(.09/.64,abs=.0001)
    assert modes['EMPIRICAL']['calibratedWinRate'] is None
    assert modes['EMPIRICAL']['empiricalCoverage']==pytest.approx(.55/.91,abs=.0001)


def test_quote_metadata_keeps_unknown_commission_unknown():
    quote=SimpleNamespace(last_price=100,pre_settlement=100,datetime='2026-10-19 10:00:00',
        volume_multiple=10,price_tick=1,margin=100,commission=float('nan'),underlying_symbol='')
    result=quote_to_snapshot('CJ701',quote)
    assert result['volumeMultiple']==10 and result['commissionPerLot'] is None


def test_research_prefers_observed_delivery_atr_to_continuous_atr(market_context):
    from algorithm_service.research import ResearchService
    bars=market_context['klines']
    history=[{'timestamp':b.timestamp.isoformat(),'open':1000,'high':1050,'low':950,'price':1000,'volume':100,'openInterest':100} for b in bars]
    feed=SimpleNamespace(execution_snapshot=lambda symbol:{'contract':'CJ701','quote':None,'history':history},
                         prediction_inputs=lambda symbol:(None,bars,None))
    raw={'data_timestamp':bars[-1].timestamp.isoformat(),'dimensions':[{'name':'test','weight':.91,'score':0,'confidence':.8,'direction':'NEUTRAL','included_in_score':True}]}
    service=ResearchService(SimpleNamespace(market_feed=feed,predict=lambda *args:raw))
    result=service.context('CJM','test')
    assert result['atr']==100 and result['atrBasis']=='实际交割合约已完成日线 ATR(14)'


@pytest.mark.parametrize('now,observed,expected',[
    ('2026-10-17T12:00:00+08:00','2026-10-16T15:00:00+08:00','CLOSED_CACHE'),
    ('2026-10-19T10:00:00+08:00','2026-10-19T09:59:59+08:00','LIVE'),
    ('2026-10-19T10:00:00+08:00','2026-10-19T09:30:00+08:00','STALE'),
])
def test_market_state_distinguishes_closed_cache_from_live_staleness(monkeypatch,now,observed,expected):
    instant=datetime.fromisoformat(now)
    class Frozen(datetime):
        @classmethod
        def now(cls,tz=None):return instant.astimezone(tz) if tz else instant
    monkeypatch.setattr('data.tqsdk_feed.datetime',Frozen)
    feed=TqSdkRealtimeFeed()
    feed.trading_dates=(date(2026,10,15),date(2026,10,16),date(2026,10,19),date(2026,10,20))
    feed.provider_symbols={'CJM':'KQ.m@CZCE.CJ','CJ701':'CZCE.CJ701'}
    feed.quotes={'CJM':{'underlyingSymbol':'CJ701','dataTimestamp':observed},
        'CJ701':{'dataTimestamp':observed,'tradingSessions':{'day':[['09:00:00','11:30:00']],'night':[]}}}
    feed.connected=True
    assert feed.execution_snapshot('CJM')['marketState']==expected


@pytest.mark.parametrize('now,expected',[('2026-10-17T12:00:00+08:00','CLOSED_CACHE'),('2026-10-19T10:00:00+08:00','WARMING')])
def test_reset_last_price_only_uses_completed_delivery_close_when_closed(monkeypatch,now,expected):
    instant=datetime.fromisoformat(now)
    class Frozen(datetime):
        @classmethod
        def now(cls,tz=None):return instant.astimezone(tz) if tz else instant
    monkeypatch.setattr('data.tqsdk_feed.datetime',Frozen)
    feed=TqSdkRealtimeFeed()
    feed.connected=True
    feed.trading_dates=(date(2026,10,16),date(2026,10,19),date(2026,10,20))
    feed.provider_symbols={'CJM':'KQ.m@CZCE.CJ','CJ701':'CZCE.CJ701'}
    feed.quotes={'CJM':{'underlyingSymbol':'CJ701','dataTimestamp':'2026-10-16T15:00:00+08:00'}}
    feed.execution_specs={'CJ701':{'tradingSessions':{'day':[['09:00:00','11:30:00']],'night':[]}}}
    feed.histories={'CJ701':[{'timestamp':'2026-10-16T00:00:00+08:00','price':8330},
                             {'timestamp':'2026-10-19T00:00:00+08:00','price':9999}]}
    result=feed.execution_snapshot('CJM')
    assert result['marketState']==expected
    if expected=='CLOSED_CACHE':
        assert result['quote']['price']==8330
        assert result['quote']['priceBasis']=='COMPLETED_DAILY_CLOSE'
        assert result['quote']['dataTimestamp']=='2026-10-16T00:00:00+08:00'
    else:assert result['quote'] is None
