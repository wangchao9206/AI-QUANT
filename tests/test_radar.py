from dataclasses import replace
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from algorithm_service.app import app,overview_radar
from algorithm_service.radar import OverviewRadar,strategy_conditions
from data.data_feed import KLineBar
from data.radar_feed import RadarCache,PublicRadarFeed,parse_global_quotes,safe_url
from data.tqsdk_feed import TqSdkRealtimeFeed


def test_overseas_uses_previous_settlement_and_original_beijing_time():
    text='var hq_str_hf_GC="102,,101,103,104,99,04:59:56,100,101,0,1,1,2026-10-17,gold,0";'
    rows=parse_global_quotes(text,datetime(2026,10,17,6,tzinfo=timezone.utc))
    assert rows[0]['changePct']==2
    assert rows[0]['dataTimestamp']=='2026-10-17T04:59:56+08:00'
    assert rows[0]['dataStatus']=='CACHED'
    assert 'CFD' in rows[0]['name']
    assert parse_global_quotes(text.replace('102,,','nan,,'))==[]
    assert parse_global_quotes(text.replace(',100,101,',',0,101,'))==[]


def test_cache_keeps_last_observation_and_backs_off_after_failure():
    cache=RadarCache()
    original={'status':'READY','items':[{'price':100}],'dataTimestamp':'2026-10-16'}
    cache.get('test',-1,lambda:original)
    def fail():raise TimeoutError('upstream')
    stale=cache.get('test',30,fail)
    assert stale['status']=='DEGRADED' and stale['dataTimestamp']=='2026-10-16'
    assert stale['items']==original['items']
    stale['items'][0]['price']=0
    assert cache.get('test',30,fail)['items'][0]['price']==100
    assert cache.get('missing',30,fail)['status']=='UNAVAILABLE'


def test_news_rejects_unsafe_undated_rows_and_keeps_original_articles(monkeypatch):
    feed=PublicRadarFeed()
    row='<li id="newsTr10"><h2 class="retitle"><a href="https://finance.eastmoney.com/a/202610161234.html"><b>原油事件</b></a></h2><p class="time">10月16日 15:00</p></li>'
    page=row+row+row.replace('原油事件','bad url').replace('https://finance.eastmoney.com/a/202610161234.html','javascript:alert(1)')+row.replace('原油事件','no time').replace('10月16日 15:00','')
    monkeypatch.setattr(feed.evidence,'_read_text',lambda url:page)
    result=feed.news()
    assert len(result['items'])==1 and result['items'][0]['title']=='原油事件'
    assert result['dataTimestamp']=='2026-10-16T15:00:00+08:00'
    assert result['items'][0]['summary']==''
    assert safe_url('javascript:alert(1)')==''


def bars():
    start=datetime(2026,7,1,tzinfo=timezone.utc)
    return [KLineBar(start+timedelta(days=i),100,101,99,100,1000,1000) for i in range(65)]


def test_strategy_scan_requires_volume_and_trend_and_distinguishes_reversal():
    history=bars()
    history[-1]=replace(history[-1],open=100,high=121,low=100,close=120,volume=2000)
    result={row['strategy']:row for row in strategy_conditions(history)}
    assert result['MOMENTUM_BREAKOUT']['signal']=='BUY'
    assert result['DUAL_THRUST']['signal']=='BUY'
    assert result['BOLLINGER_REVERSAL']['signal']=='SELL'
    history[-1]=replace(history[-1],volume=1000)
    assert strategy_conditions(history)[0]['signal']=='HOLD'
    assert strategy_conditions(history[:20])==[]
    assert all(row['signal']=='HOLD' for row in strategy_conditions(bars()))


def test_bulk_market_does_not_count_delivery_contracts_or_require_single_symbol():
    feed=TqSdkRealtimeFeed()
    observed=datetime.now(timezone.utc).isoformat()
    feed.connected=True
    feed.catalog=[{'mainSymbol':'CJM','name':'红枣','exchange':'CZCE'}, {'mainSymbol':'RBM','name':'螺纹钢','exchange':'SHFE'}]
    feed.quotes={s:{'symbol':s,'price':100,'changePct':1,'volume':10,'dataTimestamp':observed} for s in ['CJM','CJ701','RBM']}
    result=feed.overview_snapshot()
    assert [r['symbol'] for r in result['items']]==['CJM','RBM']
    radar=OverviewRadar(SimpleNamespace(market_feed=feed),None)
    result=radar.market()
    assert result['breadth']=={'up':2,'down':0,'flat':0}
    assert result['observedCount']==2
    assert len(result['sectors'])==2


def test_market_excludes_stale_missing_or_nonfinite_quotes():
    observed=datetime.now(timezone.utc).isoformat()
    good={'symbol':'CJM','name':'红枣','price':100,'changePct':1,'volume':10,'dataTimestamp':observed}
    rows=[good,{**good,'symbol':'RBM','price':float('nan')},
        {**good,'symbol':'MM','dataTimestamp':'2020-01-01T00:00:00+08:00'}]
    feed=SimpleNamespace(overview_snapshot=lambda:{'items':rows,'catalogCount':4,'connected':True,'source':'test'})
    result=OverviewRadar(SimpleNamespace(market_feed=feed),None).market()
    assert result['observedCount']==1 and result['missingCount']==3
    assert result['status']=='PARTIAL'


def test_radar_api_returns_module_degradation_without_global_failure(monkeypatch):
    monkeypatch.setattr(overview_radar,'read',lambda module:{'status':'UNAVAILABLE','items':[],'dataTimestamp':None} if module=='news' else {'status':'READY','items':[{'symbol':'CJM'}]})
    client=TestClient(app)
    assert client.get('/api/v1/research/radar/news').json()['status']=='UNAVAILABLE'
    assert client.get('/api/v1/research/radar/market').json()['items'][0]['symbol']=='CJM'
    assert client.get('/api/v1/research/radar/unknown').status_code==404


def test_overview_cache_reads_never_start_historical_downloads(tmp_path,monkeypatch):
    from data.history_manager import HistoryManager
    histories=HistoryManager(cache_dir=tmp_path)
    def unexpected(symbol):raise AssertionError('overview must not download synchronously')
    monkeypatch.setattr(histories,'fetch_from_sina',unexpected)
    assert histories.get_historical_bars('CJ0',allow_download=False)==[]
    (tmp_path/'CJ0_daily.json').write_text('{"bars":[]}',encoding='utf-8')
    assert histories.get_historical_bars('CJ0',allow_download=False)==[]


def test_signal_scan_excludes_forming_future_bar_and_counts_missing_coverage(monkeypatch):
    meta={'name':'红枣主连','exchange':'CZCE','sector':'农产品'}
    monkeypatch.setattr('algorithm_service.radar.CORE_FUTURES_SYMBOLS',{'CJ0':meta,'RB0':meta})
    today=datetime.now(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0)
    history=[replace(b,timestamp=today-timedelta(days=65-i)) for i,b in enumerate(bars())]
    history.append(replace(history[-1],timestamp=today+timedelta(days=1),close=9999,high=9999))
    histories=SimpleNamespace(get_metadata=lambda symbol:{'source':'test'} if symbol=='CJ0' else {},
        get_historical_bars=lambda symbol,**kwargs:history)
    result=OverviewRadar(None,histories).signals()
    assert result['scannedCount']==1 and result['missingCount']==1
    assert result['items']==[]
    assert result['dataTimestamp']==history[-2].timestamp.isoformat()
