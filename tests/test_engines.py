"""Tests for production engines backed by observed market data."""

from engines import MomentumOrderFlowEngine, PredictionResult, TechnicalIndicatorsEngine


def test_momentum_engine_uses_observed_series(market_context):
    result = MomentumOrderFlowEngine().predict(market_context)

    assert isinstance(result, PredictionResult)
    assert -100.0 <= result.score <= 100.0
    assert "5日动量" in result.key_metrics
    assert "成交量比" in result.key_metrics


def test_indicators_engine_uses_observed_series(market_context):
    result = TechnicalIndicatorsEngine().predict(market_context)

    assert isinstance(result, PredictionResult)
    assert "MA5" in result.key_metrics
    assert "RSI(14)" in result.key_metrics
    assert "ATR(14)" in result.key_metrics
