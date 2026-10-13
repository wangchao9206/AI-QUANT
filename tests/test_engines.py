"""
AI-QUANT 自动化测试：十一维预测子引擎单测
"""
import pytest
from engines import (
    WeatherSimulationEngine,
    MomentumOrderFlowEngine,
    TechnicalIndicatorsEngine,
    SentimentNLPEngine,
    SociologyConsumptionEngine,
    PolicyDeliveryRulesEngine,
    BehavioralPsychologyEngine,
    PragmaticExecutionEngine,
    LiuYaoMetaphysicsEngine,
    IChingPhilosophyEngine,
    QiMenDunJiaEngine,
    PredictionResult
)
from data.data_feed import FuturesDataFeed

@pytest.fixture
def mock_context():
    feed = FuturesDataFeed()
    quote = feed.get_realtime_quote("CJ2701")
    klines = feed.get_historical_klines("CJ2701", days=30)
    return {
        "symbol": "CJ2701",
        "quote": quote,
        "klines": klines
    }

def test_weather_engine(mock_context):
    engine = WeatherSimulationEngine()
    res = engine.predict(mock_context)
    assert isinstance(res, PredictionResult)
    assert -100.0 <= res.score <= 100.0
    assert 0.0 <= res.confidence <= 1.0
    assert res.dimension_key == "weather"
    assert "产区" in res.summary

def test_momentum_engine(mock_context):
    engine = MomentumOrderFlowEngine()
    res = engine.predict(mock_context)
    assert isinstance(res, PredictionResult)
    assert -100.0 <= res.score <= 100.0
    assert "动能" in res.summary

def test_indicators_engine(mock_context):
    engine = TechnicalIndicatorsEngine()
    res = engine.predict(mock_context)
    assert isinstance(res, PredictionResult)
    assert "MA5" in res.key_metrics
    assert "RSI(6)" in res.key_metrics

def test_sentiment_engine(mock_context):
    engine = SentimentNLPEngine()
    res = engine.predict(mock_context)
    assert isinstance(res, PredictionResult)
    assert res.score < 0  # 舆情冰点悲观

def test_sociology_engine(mock_context):
    engine = SociologyConsumptionEngine()
    res = engine.predict(mock_context)
    assert isinstance(res, PredictionResult)
    assert "礼盒" in res.summary

def test_policy_engine(mock_context):
    engine = PolicyDeliveryRulesEngine()
    res = engine.predict(mock_context)
    assert isinstance(res, PredictionResult)
    assert "车船板" in res.summary

def test_psychology_engine(mock_context):
    engine = BehavioralPsychologyEngine()
    res = engine.predict(mock_context)
    assert isinstance(res, PredictionResult)
    assert "枣农" in res.summary

def test_execution_engine(mock_context):
    engine = PragmaticExecutionEngine()
    res = engine.predict(mock_context)
    assert isinstance(res, PredictionResult)
    assert "空头移动防守止损" in res.key_metrics

def test_liuyao_engine(mock_context):
    engine = LiuYaoMetaphysicsEngine()
    res = engine.predict(mock_context)
    assert isinstance(res, PredictionResult)
    assert "地山谦" in res.summary
    assert "兄弟申金" in res.key_metrics["世爻六亲"]

def test_iching_engine(mock_context):
    engine = IChingPhilosophyEngine()
    res = engine.predict(mock_context)
    assert isinstance(res, PredictionResult)
    assert "山地剥" in res.summary

def test_qimen_engine(mock_context):
    engine = QiMenDunJiaEngine()
    res = engine.predict(mock_context)
    assert isinstance(res, PredictionResult)
    assert "天柱" in res.summary
    assert "惊门" in res.summary
