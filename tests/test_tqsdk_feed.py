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
    quote_to_snapshot,
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
