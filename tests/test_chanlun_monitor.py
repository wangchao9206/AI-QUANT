from copy import deepcopy
from datetime import datetime, timedelta, timezone, date
from threading import RLock
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from algorithm_service.chanlun_monitor import router_for
from chanlun_worker.data import load_dataset
from chanlun_worker.monitor import InputConflict, merge_closed, observe
from data.chanlun_monitor_source import serial_bars, sealed_bars, session_open, primary_snapshot


def candle(i):
    t=datetime(2026,10,30,9,tzinfo=timezone(timedelta(hours=8)))+timedelta(minutes=5*i)
    return {'id':i,'datetime':int(t.timestamp()*1e9),'open':100,'high':102,'low':99,'close':101,'volume':10}


def test_provider_contiguity_and_successor_proof_never_uses_pending_bar():
    bars=serial_bars([candle(i) for i in range(3)])
    now=datetime.fromisoformat(bars[-1]['timestamp'])+timedelta(minutes=20)
    assert len(sealed_bars(bars,'MIN5',now))==2  # no successor for last, even 20 min later
    assert len(sealed_bars(bars,'MIN5',now-timedelta(minutes=25)))==1
    with pytest.raises(ValueError):serial_bars([candle(0),candle(2)])
    with pytest.raises(ValueError):serial_bars([{**candle(0),'close':105}])
    assert len(serial_bars([{'id':-1},candle(0)]))==1


def test_exchange_sessions_include_friday_night_and_exclude_holiday_eve():
    tz=timezone(timedelta(hours=8));sessions={'day':[['09:00:00','15:00:00']],'night':[['21:00:00','26:30:00']]}
    dates=(date(2026,10,29),date(2026,10,30),date(2026,11,2))
    assert session_open(datetime(2026,10,30,21,1,tzinfo=tz),dates,sessions)
    assert session_open(datetime(2026,10,31,1,0,tzinfo=tz),dates,sessions)
    assert not session_open(datetime(2026,10,31,12,0,tzinfo=tz),dates,sessions)
    assert not session_open(datetime(2026,10,30,21,1,tzinfo=tz),(dates[0],dates[1],date(2026,11,9)),sessions)


def test_append_only_merge_rejects_revisions_and_lost_overlap():
    incoming=serial_bars([candle(i) for i in range(10)])
    first=merge_closed([],incoming[:5],'FU2701')
    assert merge_closed(first,incoming[3:],'FU2701')[:5]==first
    assert len(merge_closed(first,incoming[3:],'FU2701'))==10
    revised=deepcopy(incoming);revised[4]['close']=100
    with pytest.raises(InputConflict,match='修订'):merge_closed(first,revised,'FU2701')
    with pytest.raises(InputConflict,match='水位'):merge_closed(first,incoming[6:],'FU2701')


def test_prefix_rebuild_keeps_event_sequence_and_does_not_mutate_frozen_evidence():
    bars=[{**b,'providerIndex':i} for i,b in enumerate(load_dataset())]
    prefix=observe(bars[:1000],'FU2701','DAY')
    frozen=deepcopy(prefix)
    full=observe(bars,'FU2701','DAY')
    assert prefix==frozen
    assert prefix['events']==[e for e in full['events'] if e['observedIndex']<1000]
    assert full['profileHash']==prefix['profileHash']
    assert full['profileHash']!=observe(bars[:50],'FU2702','DAY')['profileHash']
    assert all(e['endIndex']<=e['observedIndex']<len(bars) for e in full['events'])


def test_disconnected_or_stalled_primary_never_emits_or_uses_public_fallback():
    now=datetime.now(timezone.utc)
    feed=SimpleNamespace(lock=RLock(),connected=False,chanlun_pump_at=now.isoformat(),chanlun_snapshots={},
        chanlun_errors={},provider_symbols={'FU2701':'SHFE.fu2701'},quotes={},execution_specs={},trading_dates=(),watch_chanlun=lambda *args:None)
    assert primary_snapshot(feed,'FU2701','MIN5',now)['status']=='DISCONNECTED'
    feed.connected=True;feed.chanlun_pump_at=(now-timedelta(seconds=16)).isoformat()
    assert primary_snapshot(feed,'FU2701','MIN5',now)['status']=='STALE'
    app=FastAPI();app.include_router(router_for(object()))
    with TestClient(app) as client:
        assert client.post('/internal/v1/chanlun/monitor',json={'symbol':'FUM','frequency':'MIN5'}).status_code==422
        response=client.post('/internal/v1/chanlun/monitor',json={'symbol':'FU2701','frequency':'MIN5'})
        assert response.json()['status']=='WAITING_DATA' and 'analysis' not in response.json()
