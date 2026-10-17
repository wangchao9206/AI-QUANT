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
        if symbol == "KQ.m@CZCE.CJ":
            return pd.DataFrame([
                {"datetime": _ns("2026-08-07"), "open": 7800, "high": 7900, "low": 7750,
                 "close": 7880, "volume": 1000, "close_oi": 500},
                {"datetime": _ns("2026-08-10"), "open": 7865, "high": 7900, "low": 7820,
                 "close": 7880, "volume": 1100, "close_oi": 550},
                {"datetime": _ns("2026-08-11"), "open": 8330, "high": 8450, "low": 8310,
                 "close": 8400, "volume": 1200, "close_oi": 600},
            ])
        assert data_length == 10000
        if symbol == "CZCE.CJ701":
            return pd.DataFrame([
                {"datetime": _ns("2026-08-10"), "open": 8340, "high": 8400, "low": 8300,
                 "close": 8325, "volume": 1100, "close_oi": 550},
                {"datetime": _ns("2026-08-11"), "open": 8330, "high": 8450, "low": 8310,
                 "close": 8400, "volume": 1200, "close_oi": 600},
            ])
        assert symbol == "CZCE.CJ609"
        old_open = float("nan") if self.missing_old_leg else 7850.0
        return pd.DataFrame([
            {"datetime": _ns("2026-08-07"), "open": 7800, "high": 7900, "low": 7750,
             "close": 7880, "volume": 1000, "close_oi": 500},
            {"datetime": _ns("2026-08-10"), "open": old_open,
             "high": 7910.0, "low": 7800.0,
             "close": 7880.0, "volume": 1000, "close_oi": 500},
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
    assert dataset.bars[1].open == 8340
    assert dataset.bars[1].close == 8325
    assert dataset.signal_bars[1].close == 7880
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
    assert cached.bars[1].close == 8325
    assert cached.signal_bars[1].close == 7880


def test_historical_replay_uses_expired_observed_archive_without_live_auth(tmp_path):
    import os
    provider = TqSdkBacktestDataProvider(cache_dir=tmp_path, username='user', password='secret',
                                        api_factory=lambda *_: FakeApi())
    provider.load('CJ0', 'KQ.m@CZCE.CJ', n=3)
    path = provider._cache_path('CJ0')
    os.utime(path, (1, 1))
    offline = TqSdkBacktestDataProvider(cache_dir=tmp_path, username='', password='')
    assert offline._read_cache(path, 3) is None
    replay = offline.cached_replay('CJM')
    assert replay is not None and replay.bars[1].close == 8325
    assert replay.roll_events[0].old_open == 7850
    assert offline.replay_catalog()[0]['startDate'] == '2026-08-07'


def test_replay_rejects_missing_contract_specs_and_old_continuous_schema(tmp_path):
    import json
    provider = TqSdkBacktestDataProvider(cache_dir=tmp_path, username='user', password='secret',
                                        api_factory=lambda *_: FakeApi())
    provider.load('CJ0', 'KQ.m@CZCE.CJ', n=3)
    path=provider._cache_path('CJ0');payload=json.loads(path.read_text())
    payload['contract_specs'].pop('CJ701');path.write_text(json.dumps(payload))
    assert provider.cached_replay('CJ0') is None
    payload['schema_version']=1;path.write_text(json.dumps(payload))
    assert provider.replay_catalog()==[]


def test_old_continuous_execution_cache_is_invalidated(tmp_path):
    import json
    provider = TqSdkBacktestDataProvider(cache_dir=tmp_path)
    path = provider._cache_path("CJ0")
    path.write_text(json.dumps({'requested_bars': 2000, 'bars': []}), encoding='utf-8')
    assert provider._read_cache(path, 3) is None


def test_unfinished_trading_day_never_enters_execution_dataset(tmp_path, monkeypatch):
    monkeypatch.setattr('data.tqsdk_backtest.completed_daily_bar',
                        lambda ts: ts.date() < date(2026, 8, 11))
    dataset = TqSdkBacktestDataProvider(cache_dir=tmp_path, username='user', password='secret',
                                      api_factory=lambda *_: FakeApi()).load('CJ0', 'KQ.m@CZCE.CJ', n=3)
    assert [b.timestamp.date() for b in dataset.bars] == [date(2026, 8, 7), date(2026, 8, 10)]


def test_missing_delivery_day_cannot_fall_back_to_continuous_price(tmp_path):
    class MissingDeliveryApi(FakeApi):
        def get_kline_serial(self, symbol, duration_seconds, data_length):
            frame = super().get_kline_serial(symbol, duration_seconds, data_length)
            return frame.iloc[:1] if symbol == 'CZCE.CJ701' else frame
    provider = TqSdkBacktestDataProvider(cache_dir=tmp_path, username='user', password='secret',
                                        api_factory=lambda *_: MissingDeliveryApi())
    from data.tqsdk_backtest import TqSdkBacktestUnavailable
    with pytest.raises(TqSdkBacktestUnavailable, match='Missing observed delivery OHLC'):
        provider.load('CJ0', 'KQ.m@CZCE.CJ', n=3)


def test_warm_cache_read_does_not_wait_for_unrelated_cold_download(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    provider = TqSdkBacktestDataProvider(cache_dir=tmp_path, username='user', password='secret',
                                        api_factory=lambda *_: FakeApi())
    provider.load('CJ0', 'KQ.m@CZCE.CJ', n=3)
    with ThreadPoolExecutor(max_workers=1) as pool:
        provider._load_lock.acquire()
        try:
            result = pool.submit(provider.load, 'CJ0', 'KQ.m@CZCE.CJ', 3).result(timeout=2)
        finally:
            provider._load_lock.release()
    assert result.bars[1].close == 8325


def test_unavailable_roll_outside_requested_window_does_not_block_recent_replay(tmp_path):
    provider = TqSdkBacktestDataProvider(cache_dir=tmp_path, username='user', password='secret',
                                        api_factory=lambda *_: FakeApi(missing_old_leg=True))
    # The partial fixture's quote-list normally contains two contracts.
    def specs(api, contracts):
        from data.tqsdk_backtest import FuturesContractSpec
        return {'CJ701':FuturesContractSpec('CJ701',5,5,6500,3)}
    provider._specs = specs
    dataset = provider.load('CJ0', 'KQ.m@CZCE.CJ', n=3, start_date=date(2026,8,11))
    assert len(dataset.bars)==1 and dataset.bars[0].close==8400
    assert not dataset.roll_events
    # A windowed cache must never masquerade as a complete full-range cache.
    assert not provider._cache_path('CJ0').exists()
    with pytest.raises(IncompleteRollData, match='both tradable legs'):
        provider.load('CJ0', 'KQ.m@CZCE.CJ', n=3)
