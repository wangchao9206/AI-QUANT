from datetime import datetime
from types import SimpleNamespace

import pandas as pd

from data.live_feed import SHANGHAI
from data.tqsdk_feed import (
    FALLBACK_SUFFIX,
    TQ_SOURCE,
    TqSdkRealtimeFeed,
    bars_to_history,
    canonical_symbol,
    provider_product,
    quote_to_microstructure,
    quote_to_snapshot,
    ticks_to_trades,
    _latest_timestamp,
)


class FakeFallback:
    def __init__(self):
        self.watched = []

    def start(self):
        pass

    def stop(self):
        pass

    def watch(self, symbol):
        self.watched.append(symbol)

    def snapshot(self, symbol):
        return {
            "quote": {
                "symbol": symbol,
                "displayName": "螺纹钢连续",
                "price": 3200.0,
                "change": 10.0,
                "changePct": 0.31,
                "source": "新浪期货",
                "dataTimestamp": "2026-10-15T09:30:00+08:00",
                "open": 3190.0,
                "high": 3210.0,
                "low": 3180.0,
                "prevClose": 3190.0,
                "prevSettlement": 3190.0,
                "volume": 100,
                "openInterest": 200,
                "dataStatus": "FRESH",
            },
            "history": [{"timestamp": "2026-10-14T15:00:00+08:00", "open": 3180.0,
                         "high": 3200.0, "low": 3170.0, "price": 3190.0,
                         "volume": 90, "openInterest": 180, "change": 5.0, "changePct": 0.16}],
            "contracts": [],
        }

    def term_snapshot(self, root):
        return {"rootSymbol": root, "dataStatus": "FRESH",
                "dataTimestamp": "2026-10-15T09:30:00+08:00", "contracts": []}

    def catalog_snapshot(self):
        return {"source": "新浪期货公开目录", "dataStatus": "FRESH",
                "dataTimestamp": "2026-10-15T09:00:00+08:00", "exchanges": []}

    def product(self, _symbol):
        return None


def test_tqsdk_symbol_mapping_covers_main_and_exchange_contracts():
    assert canonical_symbol("KQ.m@SHFE.rb") == "RBM"
    assert canonical_symbol("DCE.m2701") == "M2701"
    assert canonical_symbol("CZCE.AP701") == "AP701"
    assert provider_product("KQ.m@INE.sc") == ("INE", "SC")
    assert provider_product("CFFEX.IF2612") == ("CFFEX", "IF")


def test_quote_conversion_uses_exchange_timestamp_and_pre_settlement():
    quote = SimpleNamespace(
        last_price=3210.0,
        pre_settlement=3200.0,
        pre_close=3198.0,
        datetime="2026-10-15 09:31:02.123456",
        instrument_name="螺纹钢主连",
        open=3190.0,
        highest=3220.0,
        lowest=3188.0,
        volume=1234,
        open_interest=5678,
    )
    snapshot = quote_to_snapshot("RBM", quote)
    assert snapshot["source"] == TQ_SOURCE
    assert snapshot["change"] == 10.0
    assert snapshot["changePct"] == 0.3125
    assert snapshot["dataTimestamp"] == "2026-10-15T09:31:02.123456+08:00"
    assert snapshot["volume"] == 1234


def test_microstructure_preserves_real_five_levels_and_nulls_missing_levels():
    quote = SimpleNamespace(
        last_price=3210.0,
        datetime="2026-10-15 09:31:02.123456",
        **{f"bid_price{i}": 3210 - i for i in range(1, 5)},
        **{f"bid_volume{i}": i * 10 for i in range(1, 6)},
        **{f"ask_price{i}": 3210 + i for i in range(1, 6)},
        **{f"ask_volume{i}": i * 20 for i in range(1, 6)},
        bid_price5=float("nan"),
    )

    snapshot = quote_to_microstructure("RB2710", quote, [])

    assert len(snapshot["bids"]) == 5
    assert len(snapshot["asks"]) == 5
    assert snapshot["bids"][0] == {"level": 1, "price": 3209.0, "volume": 10}
    assert snapshot["bids"][4] == {"level": 5, "price": None, "volume": 50}
    assert snapshot["asks"][4] == {"level": 5, "price": 3215.0, "volume": 100}
    assert snapshot["source"] == TQ_SOURCE


def test_ticks_are_converted_from_cumulative_volume_without_inventing_direction():
    base = int(datetime(2026, 10, 15, 9, 31, tzinfo=SHANGHAI).timestamp() * 1_000_000_000)
    rows = pd.DataFrame([
        {"id": 1, "datetime": base, "last_price": 3200, "volume": 100,
         "amount": 1_000_000, "open_interest": 200, "ask_price1": 3201, "bid_price1": 3199},
        {"id": 2, "datetime": base + 1_000_000_000, "last_price": 3201, "volume": 103,
         "amount": 1_096_030, "open_interest": 201, "ask_price1": 3201, "bid_price1": 3200},
        {"id": 3, "datetime": base + 2_000_000_000, "last_price": 3200.5, "volume": 105,
         "amount": 1_160_040, "open_interest": 199, "ask_price1": 3201, "bid_price1": 3200},
    ])

    trades = ticks_to_trades(rows)

    assert [item["volume"] for item in trades] == [2, 3]
    assert trades[0]["side"] == "NEUTRAL"
    assert trades[1]["side"] == "BUY"
    assert trades[1]["openInterestChange"] == 1


def test_kline_conversion_uses_nanosecond_timestamp_and_ignores_nan_close():
    timestamp = int(datetime(2026, 10, 14, 0, 0, tzinfo=SHANGHAI).timestamp() * 1_000_000_000)
    rows = pd.DataFrame([
        {"datetime": timestamp, "open": 10, "high": 12, "low": 9, "close": 11,
         "volume": 100, "close_oi": 200},
        {"datetime": timestamp + 86_400_000_000_000, "open": 11, "high": 13, "low": 10,
         "close": float("nan"), "volume": 0, "close_oi": 0},
    ])
    bars = bars_to_history(rows)
    assert len(bars) == 1
    assert bars[0]["timestamp"].startswith("2026-10-14T00:00:00")
    assert bars[0]["openInterest"] == 200


def test_missing_credentials_forces_public_fallback_to_degraded(monkeypatch):
    monkeypatch.delenv("TQSDK_USERNAME", raising=False)
    monkeypatch.delenv("TQSDK_PASSWORD", raising=False)
    fallback = FakeFallback()
    feed = TqSdkRealtimeFeed(fallback=fallback)

    feed.start()
    snapshot = feed.snapshot("RBM")
    status = feed.provider_status()

    assert snapshot["quote"]["dataStatus"] == "DEGRADED"
    assert snapshot["quote"]["source"].endswith(FALLBACK_SUFFIX)
    assert status == {
        "provider": "TQSDK",
        "configured": False,
        "connected": False,
        "lastEventAt": None,
        "fallbackActive": True,
        "message": "TqSdk credentials are not configured",
    }
    assert fallback.watched == ["RBM"]


def test_disconnected_primary_snapshot_is_cached_not_fresh(monkeypatch):
    monkeypatch.setenv("TQSDK_USERNAME", "account")
    monkeypatch.setenv("TQSDK_PASSWORD", "secret")
    feed = TqSdkRealtimeFeed(fallback=FakeFallback())
    feed.quotes["RBM"] = quote_to_snapshot(
        "RBM",
        SimpleNamespace(last_price=3210, pre_settlement=3200, pre_close=3200,
                        datetime=datetime.now(SHANGHAI), instrument_name="螺纹钢主连",
                        open=3200, highest=3220, lowest=3190, volume=1, open_interest=2),
    )
    feed.histories["RBM"] = FakeFallback().snapshot("RBM")["history"]

    snapshot = feed.snapshot("RBM")

    assert snapshot["quote"]["source"] == TQ_SOURCE
    assert snapshot["quote"]["dataStatus"] == "CACHED"


def test_primary_quote_does_not_wait_for_history_warmup(monkeypatch):
    monkeypatch.setenv("TQSDK_USERNAME", "account")
    monkeypatch.setenv("TQSDK_PASSWORD", "secret")
    feed = TqSdkRealtimeFeed(fallback=FakeFallback())
    feed.connected = True
    feed.quotes["RBM"] = quote_to_snapshot(
        "RBM",
        SimpleNamespace(last_price=3210, pre_settlement=3200, pre_close=3200,
                        datetime=datetime.now(SHANGHAI), instrument_name="螺纹钢主连",
                        open=3200, highest=3220, lowest=3190, volume=1, open_interest=2),
    )

    snapshot = feed.snapshot("RBM")

    assert snapshot["quote"]["source"] == TQ_SOURCE
    assert snapshot["quote"]["dataStatus"] == "FRESH"
    assert snapshot["history"] == FakeFallback().snapshot("RBM")["history"]


def test_full_market_quotes_are_subscribed_in_one_batch(monkeypatch):
    monkeypatch.setenv("TQSDK_USERNAME", "account")
    monkeypatch.setenv("TQSDK_PASSWORD", "secret")
    feed = TqSdkRealtimeFeed(fallback=FakeFallback())
    requested = []
    entities = [SimpleNamespace(instrument_name="螺纹钢2710"),
                SimpleNamespace(instrument_name="豆粕2711"),
                SimpleNamespace(instrument_name="螺纹钢主连")]

    class FakeApi:
        def get_quote_list(self, symbols):
            requested.append(symbols)
            return entities

    providers = {
        "RB2710": "SHFE.rb2710",
        "M2711": "DCE.m2711",
        "RBM": "KQ.m@SHFE.rb",
    }

    quotes = feed._subscribe_quotes(FakeApi(), providers)

    assert requested == [["SHFE.rb2710", "DCE.m2711", "KQ.m@SHFE.rb"]]
    assert list(quotes) == ["RB2710", "M2711", "RBM"]
    assert quotes["RBM"].instrument_name == "螺纹钢主连"


def test_provider_event_time_uses_latest_observed_market_timestamp():
    assert _latest_timestamp(
        "2026-10-15T09:00:00+08:00",
        None,
        "2026-10-15T15:00:00+08:00",
    ) == "2026-10-15T15:00:00+08:00"


def test_provider_symbol_accepts_public_zero_alias_for_main_contract(monkeypatch):
    monkeypatch.setenv("TQSDK_USERNAME", "account")
    monkeypatch.setenv("TQSDK_PASSWORD", "secret")
    feed = TqSdkRealtimeFeed(fallback=FakeFallback())
    feed.provider_symbols = {"CJM": "KQ.m@CZCE.CJ"}

    assert feed.provider_symbol("CJ0") == "KQ.m@CZCE.CJ"
    assert feed.provider_symbol("CJM") == "KQ.m@CZCE.CJ"
    assert feed.provider_symbol("UNKNOWN0") is None
