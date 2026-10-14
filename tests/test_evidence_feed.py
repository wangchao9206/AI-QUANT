from datetime import datetime, timezone

from data.evidence_feed import EvidenceFeed


def test_weather_evidence_uses_upstream_observations(monkeypatch):
    payload = [
        {
            "daily": {
                "time": ["2026-10-14", "2026-10-15"],
                "temperature_2m_max": [21.3, 20.3],
                "temperature_2m_min": [10.7, 7.9],
                "precipitation_sum": [0.0, 14.5],
                "relative_humidity_2m_mean": [32, 68],
            }
        },
        {
            "daily": {
                "time": ["2026-10-14", "2026-10-15"],
                "temperature_2m_max": [20.8, 20.6],
                "temperature_2m_min": [9.4, 8.2],
                "precipitation_sum": [0.2, 0.0],
                "relative_humidity_2m_mean": [65, 61],
            }
        },
        {
            "daily": {
                "time": ["2026-10-14", "2026-10-15"],
                "temperature_2m_max": [16.9, 23.1],
                "temperature_2m_min": [10.7, 9.4],
                "precipitation_sum": [3.6, 0.0],
                "relative_humidity_2m_mean": [67, 43],
            }
        },
    ]
    feed = EvidenceFeed()
    monkeypatch.setattr(feed, "_read_json", lambda _: payload)

    evidence = feed.get_weather()

    assert evidence.status == "FRESH"
    assert evidence.sample_size == 6
    assert evidence.records[0]["region"] == "若羌"
    assert evidence.records[0]["temperature_max"] == 21.3
    assert evidence.source_url.startswith("https://api.open-meteo.com/")


def test_news_evidence_keeps_real_articles_and_filters_unrelated(monkeypatch):
    payload = {
        "data": {
            "list": [
                {
                    "title": "红枣主力合约日内跌超2%",
                    "summary": "红枣主力现报6515元/吨",
                    "showTime": "2026-10-14 09:42:33",
                    "mediaName": "东方财富Choice数据",
                    "uniqueUrl": "https://futures.eastmoney.com/a/1.html",
                },
                {
                    "title": "黄金价格上涨",
                    "summary": "其他商品市场动态",
                    "showTime": "2026-10-14 09:00:00",
                    "mediaName": "测试来源",
                    "uniqueUrl": "https://example.invalid/2",
                },
            ]
        }
    }
    feed = EvidenceFeed()
    monkeypatch.setattr(feed, "_read_json", lambda _: payload)

    evidence = feed.get_news()

    assert evidence.sample_size == 1
    assert evidence.records[0]["title"] == "红枣主力合约日内跌超2%"
    assert evidence.records[0]["media_name"] == "东方财富Choice数据"


def test_trading_rules_are_parsed_from_current_provider_page(monkeypatch):
    html = """
    <table><tr><td>红枣</td><td>CJ</td><td>2701</td><td>±7%</td><td>17%</td><td></td></tr></table>
    """
    feed = EvidenceFeed()
    monkeypatch.setattr(feed, "_read_text", lambda _: html)

    evidence = feed.get_trading_rules()

    assert evidence.sample_size == 1
    assert evidence.records[0]["contract"] == "CJ2701"
    assert evidence.records[0]["price_limit_pct"] == 7.0
    assert evidence.records[0]["margin_pct"] == 17.0


def test_ttl_cache_avoids_repeated_upstream_requests(monkeypatch):
    payload = {
        "data": {
            "list": [
                {
                    "title": "红枣成交量增加",
                    "summary": "红枣市场更新",
                    "showTime": "2026-10-14 09:42:33",
                    "mediaName": "东方财富Choice数据",
                    "uniqueUrl": "https://futures.eastmoney.com/a/1.html",
                }
            ]
        }
    }
    calls = 0

    def read_json(_):
        nonlocal calls
        calls += 1
        return payload

    feed = EvidenceFeed()
    monkeypatch.setattr(feed, "_read_json", read_json)

    first = feed.get_news()
    second = feed.get_news()

    assert first.observed_at == second.observed_at
    assert calls == 1
