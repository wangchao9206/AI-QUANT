from datetime import datetime, timezone
import httpx
import pytest

from data.live_feed import (
    LiveMarketFeed,
    contract_maturity,
    parse_contract_list,
    parse_history,
    parse_product_nodes,
    parse_quotes,
    root_symbol,
    sina_symbol,
)

QUOTE = 'var hq_str_nf_CJ2701="红枣2701,150000,6750,6770,6570,6620,6615,6620,6620,6650,6795,9,210,242886,239512,郑,红枣,2026-10-13,1";'
HISTORY = 'var _data=([{"d":"2026-10-12","o":"6750","h":"6795","l":"6710","c":"6795","v":"120","p":"240000"},{"d":"2026-10-13","o":"6750","h":"6770","l":"6570","c":"6620","v":"239512","p":"242886"}]);'
FINANCIAL_QUOTE = 'var hq_str_nf_IF2610="4144.800,4172.800,4121.400,4122.800,16978,70484869.200,24212.000,0.000,0.000,4638.600,3795.400,0.000,0.000,4219.200,4217.000,30156.000,4122.600,1,0.000,0,0.000,0,0.000,0,0.000,0,4123.600,1,0.000,0,0.000,0,0.000,0,0.000,0,2026-10-15,13:13:36,100,0,,,,,,,,,4151.541,沪深300指数期货2610";'
DIRECTORY = """ARRFUTURESNODES = {
    czce : ['郑州商品交易所', ['红枣', 'hz_qh', '27']],
    dce : ['大连商品交易所', ['豆粕', 'dp_qh', '9']],
    shfe : ['上海期货交易所', ['沪铜', 'tong_qh', '5']],
    cffex : ['中国金融期货交易所', ['沪深300指数期货', 'qz_qh', '20']],
    gfex : ['广州期货交易所', ['工业硅', 'si_qh', '20']]
};"""


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
    assert contract_maturity("CJ701", datetime(2026, 10, 15, tzinfo=timezone.utc)) == "2027-01-01"


def test_short_delivery_contract_maps_to_same_sina_contract():
    observed = datetime(2026, 10, 17, tzinfo=timezone.utc)
    assert sina_symbol("CJ701", observed) == sina_symbol("CJ2701", observed) == "CJ2701"
    assert sina_symbol("CJ612", observed) == "CJ2612"


def test_october_delivery_is_not_a_main_contract_alias():
    assert root_symbol("IF2610") == "IF"
    assert root_symbol("CJ610") == "CJ"
    assert root_symbol("IF0") == "IF"


def test_short_delivery_fallback_preserves_quote_identity_and_time(tmp_path, monkeypatch):
    observed = datetime(2026, 10, 17, tzinfo=timezone.utc)
    monkeypatch.setattr("data.live_feed.sina_symbol", lambda symbol: sina_symbol(symbol, observed))
    feed = LiveMarketFeed(str(tmp_path / "feed.json"))
    feed.symbols = {"CJ701"}
    feed.history_symbols = set()
    feed.catalog_updated = float("inf")

    def provider(request):
        assert str(request.url).endswith("list=nf_CJ2701")
        return httpx.Response(200, content=QUOTE.encode("gb18030"))

    feed.client = httpx.Client(transport=httpx.MockTransport(provider))
    feed.refresh()
    quote = feed.snapshot("CJ701")["quote"]
    assert quote["symbol"] == "CJ701"
    assert quote["price"] == 6620
    assert quote["dataTimestamp"] == "2026-10-13T15:00:00+08:00"


def test_parses_all_exchange_product_nodes_and_observed_contract_lists():
    products = parse_product_nodes(DIRECTORY)
    assert {item["exchange"] for item in products} == {"CZCE", "DCE", "SHFE", "CFFEX", "GFEX"}
    assert parse_contract_list('var _data=([{"symbol":"IF0"},{"symbol":"IF2610"}]);') == ["IF0", "IF2610"]


def test_parses_financial_futures_quote_layout():
    quote = parse_quotes(FINANCIAL_QUOTE, ["IF2610"])["IF2610"]
    assert quote["displayName"] == "沪深300指数期货2610"
    assert quote["price"] == 4122.8
    assert quote["prevSettlement"] == 4217
    assert quote["volume"] == 16978
    assert quote["openInterest"] == 24212
    assert quote["dataTimestamp"] == "2026-10-15T13:13:36+08:00"


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
