from datetime import datetime,timedelta
import json
import pytest
from data import intraday_replay as replay


@pytest.fixture
def archive(tmp_path,monkeypatch):
    monkeypatch.setenv('HISTORY_CACHE_DIR',str(tmp_path))
    root=tmp_path/'intraday-replay';root.mkdir()
    start=datetime.fromisoformat('2026-10-16T21:00:00+08:00')
    bars=[dict(timestamp=(start+timedelta(minutes=i)).isoformat(),tradingDate='2026-10-19',contract='FG701',
               open=840+i,high=842+i,low=839+i,close=841+i,volume=10,openInterest=100) for i in range(30)]
    doc=dict(schemaVersion=1,symbol='FG701',providerSymbol='CZCE.FG701',source='OBSERVED_TEST',sourceSha256='a'*64,
             generatedAt=start.isoformat(),startDate='2026-10-19',endDate='2026-10-19',bars=bars,
             spec=dict(contract='FG701',volumeMultiple=20,priceTick=1,marginPerLot=1600,commissionPerLot=6),
             dailyMacd=[dict(date='2026-10-16',availableAt='2026-10-16T15:00:00+08:00',dif=1,dea=2),
                        dict(date='2026-10-19',availableAt='2026-10-19T15:00:00+08:00',dif=2,dea=1)])
    path=root/'FG701.json';path.write_text(json.dumps(doc))
    return doc,path


def test_trading_date_keeps_friday_night_and_all_periods(archive):
    for seconds,count in ((60,30),(180,10),(300,6),(900,2)):
        d=replay.history('FG701',seconds,'2026-10-19','2026-10-19')
        assert len(d['bars'])==count
        assert d['bars'][0]['timestamp'].startswith('2026-10-16T21:00')
        assert d['bars'][0]['volume']==10*seconds//60
    assert replay.catalog()['symbols'][0]['symbol']=='FG701'


def test_aggregation_never_fills_missing_minutes(archive):
    doc,_=archive
    rows=doc['bars'][:2]+doc['bars'][3:]
    result=replay.aggregate(rows,300)
    assert len(result)==5
    assert result[0]['timestamp'].startswith('2026-10-16T21:05')


def test_chart_only_completed_candles_and_known_daily_macd(archive):
    d=replay.chart('FG701',60,datetime.fromisoformat('2026-10-16T21:02:00+08:00'))
    assert len(d['bars'])==2
    assert d['dailyContext']['date']=='2026-10-16'
    assert d['bars'][-1]['timestamp'].startswith('2026-10-16T21:01')


def test_rejects_other_contract_invalid_period_outside_dates_and_malformed_archive(archive):
    for symbol,seconds,start,end in [('FG0',60,None,None),('FG702',60,None,None),('FG701',120,None,None),('FG701',60,'2026-10-15','2026-10-19')]:
        with pytest.raises(ValueError):replay.history(symbol,seconds,start,end)
    doc,path=archive;doc['bars'][0]['low']=999
    path.write_text(json.dumps(doc));replay._read.cache_clear()
    with pytest.raises(ValueError):replay.load('FG701')
