from datetime import datetime, timezone
import httpx
import pytest

from data.live_feed import LiveMarketFeed, parse_history, parse_quotes, root_symbol, sina_symbol

QUOTE = 'var hq_str_nf_CJ2701="红枣2701,150000,6750,6770,6570,6620,6615,6620,6620,6650,6795,9,210,242886,239512,郑,红枣,2026-10-13,1";'
HISTORY = 'var _data=([{"d":"2026-10-12","o":"6750","h":"6795","l":"6710","c":"6795","v":"120","p":"240000"},{"d":"2026-10-13","o":"6750","h":"6770","l":"6570","c":"6620","v":"239512","p":"242886"}]);'


def test_parses_observed_quote_and_keeps_source_time():
    quote = parse_quotes(QUOTE, ["CJ2701"])["CJ2701"]
    assert quote["price"] == 6620
    assert quote["change"] == -175
    assert quote["changePct"] == pytest.approx(-2.575423, abs=0.000001)
    assert quote["dataTimestamp"] == "2026-10-13T15:00:00+08:00"
    assert parse_quotes('var hq_str_nf_UNKNOWN="";', ["UNKNOWN"]) == {}


def test_daily_history_is_parsed_from_provider_not_generated():
    bars = parse_history(HISTORY)
    assert len(bars) == 2
    assert bars[-1]["price"] == 6620
    assert bars[-1]["change"] == -175
    assert bars[-1]["volume"] == 239512
    with pytest.raises(ValueError):
        parse_history("invalid response")


def test_main_contract_aliases_are_provider_only():
    assert sina_symbol("CJM") == "CJ0"
    assert sina_symbol("CJ2701") == "CJ2701"
    assert root_symbol("CJM") == "CJ"
    assert root_symbol("CJ2701") == "CJ"


def test_cache_survives_restart_and_upstream_outage_without_retimestamp(tmp_path):
    path = str(tmp_path / "feed.json")
    feed = LiveMarketFeed(path)
    feed.symbols = {"CJ2701"}
    feed.client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(
        200, content=(QUOTE.encode("gb18030") if "hq.sinajs" in request.url.host else HISTORY.encode()),
    )))
    feed.refresh()
    before = feed.snapshot("CJ2701")["quote"]
    restored = LiveMarketFeed(path)
    restored.symbols = {"CJ2701"}
    def fail(request):
        raise httpx.ConnectTimeout("offline", request=request)
    restored.client = httpx.Client(transport=httpx.MockTransport(fail))
    restored.refresh()
    after = restored.snapshot("CJ2701")["quote"]
    assert after["price"] == before["price"]
    assert after["dataTimestamp"] == before["dataTimestamp"]
    assert after["dataStatus"] == "DEGRADED"
    assert restored.prediction_inputs("CJ2701")[2] == "DEGRADED"
    with pytest.raises(ValueError):
        restored.prediction_inputs("UNKNOWN")


def test_term_snapshot_uses_observed_contract_quotes(tmp_path):
    feed = LiveMarketFeed(str(tmp_path / "feed.json"))
    observed = datetime.now(timezone.utc).isoformat()
    feed.quotes = {
        "CJ2701": {"symbol": "CJ2701", "price": 6530, "dataTimestamp": observed},
        "CJ2703": {"symbol": "CJ2703", "price": 6535, "dataTimestamp": observed},
    }

    curve = feed.term_snapshot("CJM")

    assert curve["rootSymbol"] == "CJ"
    assert curve["dataStatus"] == "FRESH"
    assert [item["contract"] for item in curve["contracts"]] == ["CJ2701", "CJ2703"]
