from datetime import date, datetime
from types import SimpleNamespace

import pandas as pd
import pytest

from data.live_feed import SHANGHAI
from data.tqsdk_backtest import IncompleteRollData, TqSdkBacktestDataProvider


def _ns(day: str) -> int:
    # TqSdk daily bars start in the evening UTC but belong to the following
    # Beijing trading date.
    return int(datetime.fromisoformat(f"{day}T00:00:00+08:00").timestamp() * 1_000_000_000)


class FakeApi:
    def __init__(self, missing_old_leg: bool = False):
        self.missing_old_leg = missing_old_leg
        self.closed = False

    def query_his_cont_quotes(self, symbol, n):
        assert symbol == "KQ.m@CZCE.CJ"
        assert n == 3
        return pd.DataFrame([
            {"date": pd.Timestamp("2026-08-07"), symbol: "CZCE.CJ609"},
            {"date": pd.Timestamp("2026-08-10"), symbol: "CZCE.CJ701"},
            {"date": pd.Timestamp("2026-08-11"), symbol: "CZCE.CJ701"},
        ])

    def get_kline_serial(self, symbol, duration_seconds, data_length):
        assert duration_seconds == 86400
        if isinstance(symbol, str):
            assert symbol == "KQ.m@CZCE.CJ"
            return pd.DataFrame([
                {"datetime": _ns("2026-08-07"), "open": 7800, "high": 7900, "low": 7750,
                 "close": 7880, "volume": 1000, "close_oi": 500},
                {"datetime": _ns("2026-08-10"), "open": 8340, "high": 8400, "low": 8300,
                 "close": 8325, "volume": 1100, "close_oi": 550},
                {"datetime": _ns("2026-08-11"), "open": 8330, "high": 8450, "low": 8310,
                 "close": 8400, "volume": 1200, "close_oi": 600},
            ])
        assert symbol == ["CZCE.CJ609", "CZCE.CJ701"]
        old_open = float("nan") if self.missing_old_leg else 7850.0
        return pd.DataFrame([
            {"datetime": _ns("2026-08-10"), "open": old_open, "open1": 8340.0,
             "high": 7910.0, "low": 7800.0,
             "high1": 8400.0, "low1": 8300.0,
             "close": 7880.0, "close1": 8325.0},
        ])

    def get_quote_list(self, symbols):
        assert symbols == ["CZCE.CJ609", "CZCE.CJ701"]
        return [
            SimpleNamespace(volume_multiple=5, price_tick=5, margin=6200, commission=3),
            SimpleNamespace(volume_multiple=5, price_tick=5, margin=6500, commission=3),
        ]

    def close(self):
        self.closed = True


def test_builds_real_roll_event_from_dominant_mapping_and_both_tradable_legs(tmp_path):
    api = FakeApi()
    provider = TqSdkBacktestDataProvider(
        cache_dir=tmp_path,
        username="user",
        password="secret",
        api_factory=lambda _username, _password: api,
    )

    dataset = provider.load("CJ0", "KQ.m@CZCE.CJ", n=3, force_download=True)

    assert [bar.contract_symbol for bar in dataset.bars] == ["CJ609", "CJ701", "CJ701"]
    assert len(dataset.roll_events) == 1
    event = dataset.roll_events[0]
    assert event.execution_date == date(2026, 8, 10)
    assert event.from_contract == "CJ609"
    assert event.to_contract == "CJ701"
    assert event.old_open == 7850.0
    assert event.new_open == 8340.0
    assert event.price_gap == 490.0
    assert event.old_high == 7910.0
    assert event.old_low == 7800.0
    assert event.new_high == 8400.0
    assert event.new_low == 8300.0
    assert dataset.contract_specs["CJ701"].volume_multiple == 5
    assert dataset.contract_specs["CJ701"].price_tick == 5
    assert dataset.complete is True
    assert api.closed is True


def test_refuses_to_invent_roll_price_when_either_leg_is_missing(tmp_path):
    provider = TqSdkBacktestDataProvider(
        cache_dir=tmp_path,
        username="user",
        password="secret",
        api_factory=lambda _username, _password: FakeApi(missing_old_leg=True),
    )

    with pytest.raises(IncompleteRollData, match="both tradable legs"):
        provider.load("CJ0", "KQ.m@CZCE.CJ", n=3, force_download=True)


def test_cached_dataset_preserves_contract_provenance_without_reconnecting(tmp_path):
    first_api = FakeApi()
    first = TqSdkBacktestDataProvider(
        cache_dir=tmp_path,
        username="user",
        password="secret",
        api_factory=lambda _username, _password: first_api,
    )
    first.load("CJ0", "KQ.m@CZCE.CJ", n=3, force_download=True)

    second = TqSdkBacktestDataProvider(
        cache_dir=tmp_path,
        username="user",
        password="secret",
        api_factory=lambda _username, _password: (_ for _ in ()).throw(AssertionError("must use cache")),
    )
    cached = second.load("CJ0", "KQ.m@CZCE.CJ", n=3)

    assert cached.source == "TQSDK_REAL_DOMINANT_DAILY"
    assert cached.roll_events[0].price_gap_pct == pytest.approx(490 / 7850 * 100)
    assert cached.bars[1].timestamp.tzinfo == SHANGHAI
