from datetime import datetime, timezone

from dataclasses import replace
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from algorithm_service.app import (
    BACKTEST_CAPACITY,
    app,
    backtest_data_provider,
    history_manager,
    prediction_service,
)
from data.tqsdk_backtest import FuturesContractSpec


client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "UP"
    assert response.headers["x-trace-id"]


def test_microstructure_endpoint_exposes_real_depth_and_ticks(monkeypatch):
    monkeypatch.setattr(
        prediction_service.market_feed,
        "microstructure_snapshot",
        lambda symbol: {
            "symbol": symbol,
            "source": "天勤 TqSdk 实时行情",
            "dataStatus": "FRESH",
            "dataTimestamp": "2026-10-16T09:31:00+08:00",
            "lastPrice": 6430.0,
            "bids": [{"level": 1, "price": 6425.0, "volume": 10}],
            "asks": [{"level": 1, "price": 6430.0, "volume": 12}],
            "trades": [{
                "id": "1", "timestamp": "2026-10-16T09:30:59+08:00",
                "price": 6430.0, "volume": 2, "amount": 64300.0,
                "openInterest": 100, "openInterestChange": 1, "side": "BUY",
            }],
        },
        raising=False,
    )

    response = client.get("/api/v1/market/CJ701/microstructure")

    assert response.status_code == 200
    assert response.json()["source"] == "天勤 TqSdk 实时行情"
    assert response.json()["trades"][0]["side"] == "BUY"


def test_prediction_endpoint_returns_canonical_contract(monkeypatch):
    monkeypatch.setattr(
        prediction_service,
        "predict",
        lambda symbol, trace_id: {
            "symbol": symbol,
            "display_name": "红枣701",
            "price": 6610.0,
            "change": -185.0,
            "change_pct": -2.72,
            "composite_score": -48.2,
            "resonance": 0.82,
            "confidence": 0.76,
            "signal": "SELL",
            "action_directive": "反弹减仓 / 少量轻仓试空",
            "recommended_position_pct": -0.08,
            "target_price": 6500.0,
            "stop_loss_price": 6750.0,
            "data_status": "FRESH",
            "data_timestamp": "2026-10-13T17:00:00+08:00",
            "model_version": "1.0.0",
            "trace_id": trace_id,
            "dimensions": [],
            "event_windows": [],
        },
    )

    response = client.get(
        "/api/v1/predictions/CJ2701", headers={"X-Trace-Id": "trace-test-001"}
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["symbol"] == "CJ2701"
    assert payload["dataStatus"] == "FRESH"
    assert payload["traceId"] == "trace-test-001"
    assert payload["signal"] == "SELL"


def test_prediction_rejects_invalid_symbol():
    response = client.get("/api/v1/predictions/not_a_symbol!")

    assert response.status_code == 422


def test_market_leads_endpoint(monkeypatch):
    monkeypatch.setattr(
        prediction_service,
        "discover_leads",
        lambda trace_id="lead-scan": {
            "source": "AI-QUANT 智能线索雷达扫描引擎",
            "data_status": "FRESH",
            "scanned_count": 6,
            "leads_count": 1,
            "data_timestamp": "2026-10-15T16:00:00+08:00",
            "leads": [
                {
                    "id": "lead-cjm-resonance",
                    "symbol": "CJM",
                    "display_name": "红枣主力",
                    "exchange": "CZCE",
                    "price": 6470.0,
                    "change": 120.0,
                    "change_pct": 1.89,
                    "direction": "BULLISH",
                    "signal": "十四维高确信度同向共振 · 强烈看多",
                    "urgency": "S",
                    "composite_score": 75.5,
                    "confidence": 0.88,
                    "algorithm_type": "DIMENSION_RESONANCE",
                    "algorithm_name": "十四维全息多空共振算法",
                    "algorithm_badge": "十四维大共振",
                    "analysis": {
                        "core_anomaly": "实证量价与基差模型多头共振",
                        "market_context": "主力放量拉升突破颈线",
                        "news_driver": "主产区减产利好持续催化",
                        "key_evidence": [
                            {
                                "name": "量价动量",
                                "score": 85.0,
                                "direction": "BULLISH",
                                "summary": "突破通道上轨"
                            }
                        ]
                    },
                    "execution": {
                        "action_directive": "顺势建多仓",
                        "entry_zone": "6450.0 ~ 6490.0",
                        "target_price": 6800.0,
                        "stop_loss_price": 6320.0,
                        "recommended_position_pct": 25.0,
                        "risk_reward_ratio": "3.5:1",
                        "invalidation_condition": "跌破6320硬止损"
                    },
                    "discovered_at": "2026-10-15T16:00:00+08:00"
                }
            ]
        }
    )

    response = client.get("/api/v1/market/leads")
    assert response.status_code == 200
    payload = response.json()
    assert payload["leadsCount"] == 1
    assert payload["leads"][0]["symbol"] == "CJM"
    assert payload["leads"][0]["urgency"] == "S"
    assert payload["leads"][0]["algorithmType"] == "DIMENSION_RESONANCE"
    assert payload["leads"][0]["analysis"]["coreAnomaly"] == "实证量价与基差模型多头共振"
    assert payload["leads"][0]["execution"]["riskRewardRatio"] == "3.5:1"


def test_real_lead_classifier_uses_only_returned_evidence(monkeypatch):
    prediction_service._leads_cache = None
    prediction_service._leads_cache_time = None

    def fake_prediction(symbol, trace_id):
        observed_at = datetime(2026, 10, 15, 8, tzinfo=timezone.utc).isoformat()
        dimensions = [
            {
                "key": f"dimension_{idx}",
                "name": f"实证维度{idx}",
                "score": 70.0,
                "direction": "BULLISH",
                "confidence": 0.8,
                "summary": f"来源指标{idx}确认上行",
                "recommendation": "观察",
                "category": "EMPIRICAL",
                "data_status": "FRESH",
                "included_in_score": True,
                "weight": 0.05,
                "source_name": "TEST_SOURCE",
                "source_url": "",
                "observed_at": observed_at,
                "sample_size": 100,
                "key_metrics": {},
            }
            for idx in range(8)
        ]
        return {
            "symbol": symbol,
            "display_name": symbol,
            "price": 100.0,
            "change": 2.0,
            "change_pct": 2.0,
            "composite_score": 70.0,
            "resonance": 0.8,
            "confidence": 0.8,
            "signal": "BUY",
            "action_directive": "观察",
            "recommended_position_pct": 10.0,
            "target_price": 106.0,
            "stop_loss_price": 97.0,
            "data_status": "FRESH",
            "data_timestamp": observed_at,
            "dimensions": dimensions,
            "cultural_references": [],
        }

    monkeypatch.setattr(prediction_service, "predict", fake_prediction)
    result = prediction_service.discover_leads("real-classifier-test")

    assert result["leads_count"] > 0
    text = " ".join(
        f"{lead['analysis']['core_anomaly']} {lead['analysis']['market_context']} {lead['analysis']['news_driver']}"
        for lead in result["leads"]
    )
    assert "p < 0.01" not in text
    assert "主动买盘占比" not in text
    assert "三年历史低位" not in text
    assert "75%" not in text
    assert all(lead["data_status"] == "FRESH" for lead in result["leads"])


def test_backtest_presets():
    response = client.get("/api/v1/backtest/presets")
    assert response.status_code == 200
    data = response.json()
    assert "strategies" in data
    assert len(data["strategies"]) >= 5
    strategy_ids = [s["id"] for s in data["strategies"]]
    assert "HOLISTIC_14D" in strategy_ids
    assert "MOMENTUM_BREAKOUT" in strategy_ids
    assert "DUAL_THRUST" in strategy_ids
    assert "BUY_AND_HOLD" in strategy_ids
    assert "symbols" in data
    assert len(data["symbols"]) >= 30


def test_history_status():
    response = client.get("/api/v1/data/history/status")
    assert response.status_code == 200
    data = response.json()
    assert "totalSymbols" in data
    assert "totalBars" in data
    assert data["totalSymbols"] >= 80
    assert data["totalBars"] > 200000


def test_backtest_run_dual_thrust(monkeypatch):
    bars = [
        replace(bar, contract_symbol="CJ701")
        for bar in history_manager.get_historical_bars("CJ0")
    ]
    monkeypatch.setattr(
        prediction_service.market_feed,
        "provider_symbol",
        lambda symbol: "KQ.m@CZCE.CJ",
        raising=False,
    )
    monkeypatch.setattr(
        backtest_data_provider,
        "load",
        lambda *args, **kwargs: SimpleNamespace(
            source="TQSDK_REAL_DOMINANT_DAILY",
            generated_at=datetime(2026, 10, 15, 8, tzinfo=timezone.utc),
            provider_symbol="KQ.m@CZCE.CJ",
            bars=bars,
            roll_events=[],
            contract_specs={
                "CJ701": FuturesContractSpec("CJ701", 5, 5, 6500, 3),
            },
        ),
    )
    response = client.post(
        "/api/v1/backtest/run",
        json={
            "symbol": "CJ0",
            "strategy": "DUAL_THRUST",
            "initial_capital": 1000000.0,
            "position_pct": 30.0,
            "start_date": "2024-01-01",
            "end_date": "2026-10-15",
        },
    )
    assert response.status_code == 200
    res = response.json()
    assert res["symbol"] == "CJ0"
    assert "Dual Thrust" in res["strategyName"]
    assert "totalReturnPct" in res
    assert "maxDrawdownPct" in res
    assert "sharpeRatio" in res
    assert "dailyEquity" in res
    assert "tradeLogs" in res
    assert "rollTrades" in res
    assert "totalRollYieldPct" in res
    assert "rollCostTotal" in res
    assert "includeRollCost" in res
    assert res["executionModel"] == "NEXT_BAR_OPEN"


def test_simulation_history_exposes_real_contract_provenance(monkeypatch):
    bars = [
        replace(bar, contract_symbol="CJ701")
        for bar in history_manager.get_historical_bars("CJ0")[-30:]
    ]
    monkeypatch.setattr(
        prediction_service.market_feed,
        "provider_symbol",
        lambda symbol: "KQ.m@CZCE.CJ",
        raising=False,
    )
    monkeypatch.setattr(
        backtest_data_provider,
        "load",
        lambda *args, **kwargs: SimpleNamespace(
            source="TQSDK_REAL_DOMINANT_DAILY",
            generated_at=datetime(2026, 10, 15, 8, tzinfo=timezone.utc),
            provider_symbol="KQ.m@CZCE.CJ",
            bars=bars,
            roll_events=[],
            contract_specs={
                "CJ701": FuturesContractSpec("CJ701", 5, 5, 6500, 3),
            },
        ),
    )

    response = client.get("/internal/v1/simulation/history/CJ0")

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "TQSDK_REAL_DOMINANT_DAILY"
    assert payload["bars"][0]["contract"] == "CJ701"
    assert payload["contractSpecs"]["CJ701"]["volumeMultiple"] == 5


@pytest.mark.parametrize(
    "payload",
    [
        {"strategy": "UNKNOWN"},
        {"initialCapital": -1},
        {"positionPct": 101},
        {"feeRate": -0.01},
        {"slippage": -1},
        {"leverage": 11},
        {"marginRate": 0},
        {"startDate": "2025-02-01", "endDate": "2025-01-01"},
    ],
)
def test_backtest_rejects_unsafe_parameters(payload):
    response = client.post("/api/v1/backtest/run", json={"symbol": "CJ0", **payload})
    assert response.status_code == 422


def test_backtest_rejects_when_capacity_is_exhausted():
    acquired = 0
    while BACKTEST_CAPACITY.acquire(blocking=False):
        acquired += 1
    assert acquired > 0
    try:
        response = client.post(
            "/api/v1/backtest/run",
            json={"symbol": "CJ0", "strategy": "DUAL_THRUST"},
        )
    finally:
        for _ in range(acquired):
            BACKTEST_CAPACITY.release()

    assert response.status_code == 429
    assert response.headers["retry-after"] == "5"


def test_specific_contract_history_is_not_silently_relabelled():
    response = client.get("/api/v1/market/CJ2701/history?limit=50")
    assert response.status_code in (404, 503)


def test_history_endpoint_returns_more_than_240_bars():
    response = client.get("/api/v1/market/CJ0/history?limit=5000")
    assert response.status_code == 200
    res = response.json()
    assert res["symbol"] == "CJ0"
    assert res["seriesSymbol"] == "CJ0"
    assert res["seriesType"] == "CONTINUOUS"
    assert res["dataStatus"] == "CACHED"
    points = res["points"]
    # 之前仅有240根，现在应包含全量历史（CJ0共有1800+根日K）
    assert len(points) > 1000
    first_pt = points[0]
    assert "open" in first_pt
    assert "high" in first_pt
    assert "low" in first_pt
    assert "volume" in first_pt
