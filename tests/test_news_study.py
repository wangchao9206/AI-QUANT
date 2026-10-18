from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
import json
from pathlib import Path

import pytest

from algorithm_service.paper_chart import visible_bars
from algorithm_service.news_analysis import interpret
from algorithm_service.event_study import price_window, event_study
from data.news_sources import NewsCollector, SOURCES, parse_rss, parse_official_html


RSS = '''<rss><channel><item><title>FOMC monetary policy</title><link>https://www.federalreserve.gov/release.htm</link><pubDate>Sun, 15 Mar 2020 17:00:00 -0400</pubDate></item></channel></rss>'''


def test_publication_timezone_and_day_precision_are_not_inferred_from_url():
    row = parse_rss(RSS, {})[0]
    assert row['publishedAt'] == '2020-03-15T17:00:00-04:00'
    assert parse_rss(RSS.replace(' -0400', ''), {}) == []
    source = next(s for s in SOURCES if s['id'] == 'ndrc')
    html = '<li><a href="./202001/t20200101_1.html">公告</a><span>2020/01/02</span></li>'
    row = parse_official_html(html, source)[0]
    assert row['publishedAt'] == '2020-01-02T00:00:00+08:00'
    assert row['timePrecision'] == 'DAY'
    assert parse_official_html(html.replace('<span>2020/01/02</span>', ''), source) == []
    assert parse_official_html(html.replace('./202001/t20200101_1.html', 'javascript:alert(1)'), source) == []


def test_partial_source_failure_retains_original_fetch_and_publication_times(tmp_path):
    def read(url):
        if 'federalreserve.gov' in url: return RSS
        raise TimeoutError('unavailable')
    collector = NewsCollector(read, tmp_path/'cache.json')
    first = collector.collect()
    assert first['status'] == 'PARTIAL'
    assert len(first['items']) == 1
    row = first['items'][0]
    assert row['sourceTier'] == 'PRIMARY' and row['sourceStatus'] == 'READY'
    collector.read_text = lambda url: (_ for _ in ()).throw(TimeoutError())
    second = collector.collect()
    assert second['items'][0]['sourceStatus'] == 'CACHED'
    assert second['items'][0]['fetchedAt'] == row['fetchedAt']
    assert second['items'][0]['publishedAt'] == row['publishedAt']
    assert any(s['status']=='UNAVAILABLE' for s in second['sources'])
    assert '90天' in next(s for s in second['sources'] if s['id']=='fed')['message']


def test_rules_show_conditions_and_counterevidence_without_trade_signal():
    item = interpret({'title':'FOMC monetary policy decision', 'topic':'产业资讯'})
    assert 'AUM' in item['relatedSymbols'] and 'TM' in item['relatedSymbols']
    assert item['topic']=='宏观政策'
    assert item['analysis'][0]['checks']
    assert '反向' in item['analysis'][0]['conditions']
    assert 'signal' not in item and 'confidence' not in item
    assert interpret({'title':'spoil prevention','topic':'产业资讯'})['eventTypes']==[]
    unknown = interpret({'title':'会议通知','topic':'产业资讯'})
    assert unknown['relatedSymbols']==[] and '暂不推断' in unknown['analysis'][0]['conditions']


def bar(stamp, price=100):
    return SimpleNamespace(timestamp=stamp, contract_symbol='CJ505', open=price,high=price+2,
                           low=price-2,close=price+1,volume=20,open_interest=30)


def test_paper_context_filters_before_limiting_and_preserves_actual_ohlc():
    clock = datetime(2025,1,6,7,tzinfo=timezone.utc)
    rows = [bar(clock+timedelta(days=i),100+i) for i in range(-10,11)]
    result = visible_bars(rows, clock, 3)
    assert len(result)==3 and result[-1]['timestamp']==clock
    assert result[-1]['open']==100 and result[-1]['close']==101
    assert result[0]['timestamp']==clock-timedelta(days=2)
    with pytest.raises(ValueError): visible_bars(rows, clock.replace(tzinfo=None), 3)


def test_paper_chart_api_validates_clock_and_returns_no_later_bars(monkeypatch):
    from fastapi.testclient import TestClient
    from algorithm_service.app import app, backtest_data_provider
    clock = datetime(2025,1,6,7,tzinfo=timezone.utc)
    monkeypatch.setattr(backtest_data_provider, 'cached_replay', lambda symbol: SimpleNamespace(
        source='observed', bars=[bar(clock-timedelta(days=1)), bar(clock), bar(clock+timedelta(days=1))]))
    client = TestClient(app)
    response = client.get('/internal/v1/simulation/chart/CJ0', params={'as_of':clock.isoformat(), 'limit':240})
    assert response.status_code == 200
    assert len(response.json()['bars']) == 2
    assert client.get('/internal/v1/simulation/chart/CJ0', params={'as_of':'2025-01-06T07:00:00','limit':240}).status_code == 400
    assert client.get('/internal/v1/simulation/chart/CJ0', params={'as_of':clock.isoformat(),'limit':1001}).status_code == 422


def test_event_window_uses_next_sessions_and_refuses_uncovered_events():
    start = datetime(2025,1,1,tzinfo=timezone.utc)
    bars = [bar(start+timedelta(days=i),100+i) for i in range(60)]
    event = date(2025,1,25)
    result = price_window(bars,event)
    assert result['baselineDate']=='2025-01-24'
    assert result['after5Date']=='2025-01-30'
    assert result['after20Date']=='2025-02-14'
    assert result['after5Pct']==round((130/124-1)*100,3)
    assert price_window(bars,date(2024,1,1))['status']=='INSUFFICIENT'
    assert price_window(bars[:10]+bars[40:],event)['status']=='INSUFFICIENT'


def test_curated_study_marks_background_and_unproven_earliest_sources():
    class NoHistory:
        def get_historical_bars(self, symbol, *, allow_download):
            assert allow_download is False
            return []
    result = event_study(NoHistory())
    assert len(result['items'])==9
    assert sum(i['role']=='窗口外背景' for i in result['items'])==1
    assert all(i['earliestStatus'] and i['limitation'] and i['sources'] for i in result['items'])
    assert all(s['url'].startswith('https://') for i in result['items'] for s in i['sources'])
    assert all(w['status']=='INSUFFICIENT' for i in result['items'] for w in i['windows'])
