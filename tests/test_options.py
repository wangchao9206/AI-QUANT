from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from algorithm_service.options import (ScenarioRequest, analyze_contract, expiry_scenario,
                                       implied_volatility, model_values, router_for)
from data.options_feed import OptionsFeedState, quote_snapshot

NOW = datetime.now(timezone.utc) - timedelta(seconds=1)
EXPIRY = (NOW + timedelta(days=90)).isoformat()
CHAIN = {"underlyingType": "FUTURE", "underlyingSymbol": "DCE.m2701"}


@pytest.fixture(autouse=True)
def stable_feed_freshness_clock(monkeypatch):
    # Collection and unrelated suites can exceed the production 15-second freshness
    # window. Keep these quote fixtures and the feed clock on the same instant.
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            value = NOW + timedelta(seconds=1)
            return value.astimezone(tz) if tz else value.replace(tzinfo=None)
    monkeypatch.setattr('data.options_feed.datetime', Clock)


def quote(**kwargs):
    return {"last_price": 10.0, "bid_price1": 9.0, "ask_price1": 11.0,
            "bid_volume1": 2, "ask_volume1": 3, "volume": 15, "open_interest": 30,
            "datetime": NOW.isoformat(), "exercise_type": "A", **kwargs}


def contract(**kwargs):
    return {"symbol": "DCE.m2701-C-100", "optionClass": "CALL", "strike": 100,
            "expiry": EXPIRY, "exerciseType": "A", "volumeMultiple": 10,
            **quote_snapshot(quote()), **kwargs}


def underlying(**kwargs):
    return {"lastPrice": 100, "dataTimestamp": NOW.isoformat(), **kwargs}


class FakeApi:
    def __init__(self):
        self.queries = []
        self.subscriptions = []
        self.quotes = {"DCE.m2701": quote(last_price=100),
                       "DCE.m2701-C-100": quote(), "CFFEX.IO2701-P-4000": quote(),
                       "SSE.000300": quote(last_price=4000)}

    def query_quotes(self, **kwargs):
        self.queries.append(kwargs)
        return ["DCE.m2701-C-100", "CFFEX.IO2701-P-4000", "SSE.10000001"]

    def query_symbol_info(self, symbols):
        rows = []
        for symbol in symbols:
            if symbol in ("DCE.m2701", "SSE.000300"):
                rows.append({"instrument_id": symbol, "ins_class": "FUTURE" if symbol.startswith("DCE") else "INDEX"})
            else:
                rows.append({"instrument_id": symbol, "ins_class": "OPTION", "product_id": symbol.split(".")[0],
                             "underlying_symbol": "DCE.m2701" if symbol.startswith("DCE") else "SSE.000300",
                             "option_class": "CALL" if symbol.startswith("DCE") else "PUT",
                             "strike_price": 100 if symbol.startswith("DCE") else 4000,
                             "expire_datetime": datetime.fromisoformat(EXPIRY).timestamp(),
                             "volume_multiple": 10, "exercise_type": "A"})
        return pd.DataFrame(rows)

    def get_quote_list(self, symbols):
        self.subscriptions.append(symbols)
        return [self.quotes[s] for s in symbols]


def prepared():
    state, api = OptionsFeedState(), FakeApi()
    state.catalog_snapshot(True, True)
    state.poll(api)
    key = next(k for k, c in state.chains.items() if c["exchange"] == "DCE")
    return state, api, key


def test_catalog_is_lazy_preserves_identifiers_and_distinguishes_actual_index_underlying():
    state, api = OptionsFeedState(), FakeApi()
    state.poll(api)
    assert api.queries == []
    assert state.catalog_snapshot(False, False)["dataStatus"] == "UNAVAILABLE"
    state.poll(api)
    assert api.queries == [{"ins_class": "OPTION", "expired": False}]
    assert api.subscriptions == []
    chains = state.catalog_snapshot(True, True)["chains"]
    assert len(chains) == 2  # ETF options deliberately excluded.
    index_chain = next(c for c in chains if c["exchange"] == "CFFEX")
    assert index_chain["underlyingType"] == "INDEX"
    assert index_chain["underlyingSymbol"] == "SSE.000300"


def test_batch_subscription_warming_cached_disconnect_and_snapshot_isolation():
    state, api, key = prepared()
    first = state.chain_snapshot(key, True, 15)
    assert first["dataStatus"] == "WARMING"
    assert "lastPrice" not in first["contracts"][0]
    state.poll(api)
    assert api.subscriptions == [["DCE.m2701", "DCE.m2701-C-100"]]
    result = state.chain_snapshot(key, True, 15)
    assert result["dataStatus"] == "FRESH"
    assert result["contracts"][0]["symbol"] == "DCE.m2701-C-100"
    result["contracts"][0]["lastPrice"] = 999
    disconnected = state.chain_snapshot(key, False, 15)
    assert disconnected["dataStatus"] == "CACHED"
    assert disconnected["contracts"][0]["lastPrice"] == 10
    state.reset_session()
    state.poll(api)
    assert len(api.subscriptions) == 2


def test_missing_timestamp_and_nan_remain_unavailable():
    result = quote_snapshot(quote(datetime="", last_price=float("nan"), bid_price1=float("inf")))
    assert result["dataTimestamp"] is None
    assert result["lastPrice"] is None
    assert result["bidPrice"] is None


def test_discovery_and_subscription_failures_are_isolated_and_capacity_is_bounded():
    state, api = OptionsFeedState(), FakeApi()
    state.catalog_snapshot(True, True)
    api.query_quotes = lambda **_: (_ for _ in ()).throw(RuntimeError("private provider details"))
    state.poll(api)
    result = state.catalog_snapshot(True, True)
    assert result["dataStatus"] == "UNAVAILABLE"
    assert "private" not in result["message"]
    state, api, key = prepared()
    state.chain_snapshot(key, True, 15)
    state.MAX_SUBSCRIPTIONS = 1
    state.poll(api)
    assert state.chain_snapshot(key, True, 15)["dataStatus"] == "UNAVAILABLE"
    assert api.subscriptions == []


def test_failed_subscription_retries_without_dropping_catalog_or_futures_connection():
    state, api, key = prepared()
    state.chain_snapshot(key, True, 15)
    subscribe = api.get_quote_list
    api.get_quote_list = lambda _: (_ for _ in ()).throw(RuntimeError("permission denied"))
    state.poll(api)
    result = state.chain_snapshot(key, True, 15)
    assert result["dataStatus"] == "UNAVAILABLE"
    assert "订阅失败" in result["message"]
    assert state.catalog_snapshot(True, True)["chains"]
    api.get_quote_list = subscribe
    state._retry_at.clear()
    state.poll(api)
    assert state.chain_snapshot(key, True, 15)["dataStatus"] == "FRESH"


def test_empty_provider_catalog_is_unavailable_and_does_not_erase_observed_catalog():
    state, api, key = prepared()
    api.query_quotes = lambda **_: []
    state._next_discovery = 0
    state.poll(api)
    result = state.catalog_snapshot(True, True)
    assert result["dataStatus"] == "CACHED"
    assert result["message"]
    assert any(c["id"] == key for c in result["chains"])


def test_bsm_matches_published_reference_and_black76_put_call_parity():
    values = model_values(100, 100, 1, .2, .05, 0, "CALL", "INDEX")
    assert values["price"] == pytest.approx(10.450583572, abs=1e-8)
    assert values["delta"] == pytest.approx(.6368306512, abs=1e-8)
    call = model_values(110, 100, .7, .3, .025, 0, "CALL", "FUTURE")["price"]
    put = model_values(110, 100, .7, .3, .025, 0, "PUT", "FUTURE")["price"]
    import math
    assert call - put == pytest.approx(math.exp(-.025 * .7) * 10)


@pytest.mark.parametrize("kind", ["CALL", "PUT"])
@pytest.mark.parametrize("underlying_type", ["FUTURE", "INDEX"])
def test_greeks_agree_with_independent_price_bumps_and_iv_roundtrips(kind, underlying_type):
    def value(s=105, t=.6, vol=.31):
        return model_values(s, 100, t, vol, .03, .015, kind, underlying_type)["price"]
    values = model_values(105, 100, .6, .31, .03, .015, kind, underlying_type)
    ds, dt, dv = .01, 1e-5, 1e-5
    assert values["delta"] == pytest.approx((value(s=105+ds)-value(s=105-ds))/(2*ds), rel=1e-6)
    assert values["gamma"] == pytest.approx((value(s=105+ds)-2*value()+value(s=105-ds))/ds**2, rel=1e-5)
    assert values["theta"] == pytest.approx((value(t=.6-dt)-value(t=.6+dt))/(2*dt*365), rel=1e-6)
    assert values["vega"] == pytest.approx((value(vol=.31+dv)-value(vol=.31-dv))/(2*dv*100), rel=1e-6)
    iv, reason = implied_volatility(value(), 105, 100, .6, .03, .015, kind, underlying_type)
    assert iv == pytest.approx(.31)
    assert reason is None


def test_american_model_is_explicitly_reference_and_expired_or_unsynchronized_inputs_do_not_get_greeks():
    result = analyze_contract(contract(), CHAIN, underlying(), .02, 0)
    assert result["riskStatus"] == "EUROPEAN_APPROXIMATION"
    assert result["referencePrice"] == 10
    assert result["priceBasis"] == "MID"
    assert result["iv"] > 0
    for row, under in [(contract(exerciseType=None), underlying()),
                       (contract(expiry=(NOW-timedelta(seconds=1)).isoformat()), underlying()),
                       (contract(), underlying(dataTimestamp=(NOW-timedelta(minutes=6)).isoformat())),
                       (contract(), underlying(lastPrice=None)),
                       (contract(bidPrice=12, askPrice=11), underlying())]:
        risk = analyze_contract(row, CHAIN, under, .02, 0)
        assert risk["riskStatus"] == "UNAVAILABLE"
        assert risk["iv"] is None and risk["delta"] is None
        assert risk["riskReason"]
    no_quote_time = analyze_contract(contract(dataTimestamp=None, bidPrice=None), CHAIN, underlying(), .02, 0)
    assert no_quote_time["referencePrice"] is None


def test_last_price_fallback_and_european_price_bounds_are_disclosed():
    result = analyze_contract(contract(bidPrice=None), CHAIN, underlying(), .02, 0)
    assert result["priceBasis"] == "LAST"
    assert result["priceNote"]
    result = analyze_contract(contract(bidPrice=120, askPrice=121), CHAIN, underlying(), .02, 0)
    assert result["iv"] is None
    assert "区间" in result["riskReason"]


@pytest.mark.parametrize("kind,side,max_loss,max_profit", [
    ("CALL", "BUY", 200, None), ("CALL", "SELL", None, 200),
    ("PUT", "BUY", 200, 1800), ("PUT", "SELL", 1800, 200),
])
def test_expiry_payoff_extrema_breakeven_and_contract_units(kind, side, max_loss, max_profit):
    request = ScenarioRequest(chainId="chain", symbol="contract", side=side, lots=2)
    result = expiry_scenario(contract(optionClass=kind), underlying(), request)
    assert result["premiumAmount"] == 200
    assert result["maxLoss"] == max_loss
    assert result["maxProfit"] == max_profit
    point = next(p for p in result["points"] if p["underlyingPrice"] == result["breakeven"])
    assert point["pnl"] == pytest.approx(0)
    assert result["points"][0]["underlyingPrice"] == 0


def test_api_validates_catalog_membership_and_bad_quantity_without_contacting_sdk():
    state, api, key = prepared()
    state.chain_snapshot(key, True, 15)
    state.poll(api)
    app = FastAPI()
    app.include_router(router_for(SimpleNamespace(options=state, connected=True, configured=True, freshness_seconds=15)))
    client = TestClient(app)
    assert client.get("/api/v1/options/catalog").status_code == 200
    data = client.get("/api/v1/options/chain", params={"chainId": key}).json()
    assert data["contracts"][0]["risk"]["approximation"] is True
    assert data["assumptions"]["rateSource"] == "USER_ASSUMPTION"
    assert client.get("/api/v1/options/chain", params={"chainId": "unknown"}).status_code == 404
    assert client.get("/api/v1/options/chain", params={"chainId": key, "rate": "nan"}).status_code == 422
    body = {"chainId": key, "symbol": "DCE.m2701-C-100", "lots": 1}
    assert client.post("/api/v1/options/scenario", json=body).status_code == 200
    for lots in (0, -1, 1.5, True, 10001):
        assert client.post("/api/v1/options/scenario", json={**body, "lots": lots}).status_code == 422
    assert client.post("/api/v1/options/scenario", json={**body, "symbol": "fake"}).status_code == 404


def test_non_tqsdk_feed_returns_explicit_unavailable():
    app = FastAPI()
    app.include_router(router_for(SimpleNamespace()))
    assert TestClient(app).get("/api/v1/options/catalog").status_code == 503
