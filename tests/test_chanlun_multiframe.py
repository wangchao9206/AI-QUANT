from copy import deepcopy
from datetime import datetime,timedelta,timezone
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from algorithm_service.chanlun_multiframe import reconstruct,router_for
from chanlun_worker.data import load_dataset


def sources():
    start=datetime(2026,10,1,tzinfo=timezone.utc)
    result={}
    for frequency,minutes in [('MIN5',5),('MIN30',30)]:
        bars=[{**b,'providerIndex':i,'timestamp':(start+timedelta(minutes=i*minutes)).isoformat(),
               'date':(start+timedelta(minutes=i*minutes)).date().isoformat()} for i,b in enumerate(load_dataset()[:400])]
        result[frequency]={'bars':bars,'receiptAt':'2026-10-31T00:00:00Z','source':'SYNTHETIC_TEST_SERIAL'}
    return result


def test_cutoff_uses_successor_time_before_calculation_and_future_changes_do_not_repaint():
    captured=sources();now=datetime(2026,10,31,tzinfo=timezone.utc);cutoff=datetime(2026,10,3,tzinfo=timezone.utc)
    result=reconstruct(captured,'FU2701',cutoff,now)
    frames={f['frequency']:f for f in result['frames']}
    assert frames['MIN30']['analysis']['observedBars']==96
    assert frames['MIN5']['analysis']['observedBars']==399
    assert all(datetime.fromisoformat(b['sealedByTimestamp'])<=cutoff for f in result['frames'] for b in f['analysis']['bars'])
    revised=deepcopy(captured)
    for s in revised.values():
        for b in s['bars']:
            if datetime.fromisoformat(b['timestamp'])>cutoff:
                for k in ('open','high','low','close'):b[k]*=3
    assert reconstruct(revised,'FU2701',cutoff,now)==result
    assert result['executable'] is False


def test_higher_timeframe_not_confirmed_at_lower_bar_start_and_no_fallback_to_future():
    data=sources();now=datetime(2026,10,31,tzinfo=timezone.utc)
    cut=datetime(2026,10,2,12,5,tzinfo=timezone.utc)
    r=reconstruct(data,'FU2701',cut,now)
    high=next(f for f in r['frames'] if f['frequency']=='MIN30')
    assert high['analysis']['bars'][-1]['timestamp']=='2026-10-02T11:30:00+00:00'
    assert high['lastSealedBy']=='2026-10-02T12:00:00+00:00'
    with pytest.raises(ValueError,match='不足 50'):reconstruct(data,'FU2701',datetime(2026,10,1,2,tzinfo=timezone.utc),now)
    with pytest.raises(ValueError,match='不能晚于'):reconstruct(data,'FU2701',now+timedelta(seconds=1),now)


def test_private_endpoint_requires_zoned_time_and_verified_frequency_selection():
    app=FastAPI();app.include_router(router_for(object()));client=TestClient(app)
    for body in ({'symbol':'FUM'},{'symbol':'FU2701','frames':'FAKE_MINUTE'},
                 {'symbol':'FU2701','asOf':'2026-10-01T10:00:00'}):
        assert client.post('/internal/v1/chanlun/multiframe',json=body).status_code==422
    assert client.post('/internal/v1/chanlun/multiframe',json={'symbol':'FU2701','frames':'PAIR'}).json()['status']=='WAITING_INPUT'
