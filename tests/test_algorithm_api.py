from fastapi.testclient import TestClient

from algorithm_service.app import app, prediction_service


client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "UP"
    assert response.headers["x-trace-id"]


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
