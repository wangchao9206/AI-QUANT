"""
AI-QUANT 自动化测试：多维全息合成与回测集成测试
"""
import os
import pytest
from engines.fusion_engine import HolisticFusionEngine, FusionDecision
from data.data_feed import FuturesDataFeed
from reporting.reporter import ReportGenerator
from backtesting.backtester import QuantitativeBacktester

def test_holistic_fusion_and_decision():
    feed = FuturesDataFeed()
    quote = feed.get_realtime_quote("CJ2701")
    klines = feed.get_historical_klines("CJ2701", days=30)
    context = {"symbol": "CJ2701", "quote": quote, "klines": klines}

    engine = HolisticFusionEngine()
    decision = engine.evaluate_all(context)

    assert isinstance(decision, FusionDecision)
    assert decision.symbol == "CJ2701"
    assert -100.0 <= decision.composite_score <= 100.0
    assert 0.0 <= decision.directional_resonance <= 1.0
    assert decision.primary_signal in ("STRONG_SELL", "SELL", "HOLD", "BUY", "STRONG_BUY")
    assert set(decision.dimension_results) == {
        "weather", "momentum", "indicators", "sentiment", "supply_demand",
        "policy", "positioning", "execution", "spread", "term_structure", "liquidity",
    }
    assert set(decision.cultural_references) == {"liuyao", "iching", "qimen"}
    assert decision.target_price_tp1 > 0
    assert decision.stop_loss_price > 0

def test_reporting_exports(tmp_path):
    feed = FuturesDataFeed()
    quote = feed.get_realtime_quote("CJ2701")
    klines = feed.get_historical_klines("CJ2701", days=30)
    engine = HolisticFusionEngine()
    decision = engine.evaluate_all({"symbol": "CJ2701", "quote": quote, "klines": klines})

    reporter = ReportGenerator(output_dir=str(tmp_path))
    md_file = reporter.export_markdown_report(decision, quote)
    html_file = reporter.export_html_dashboard(decision, quote)
    json_file = reporter.export_json(decision)

    assert os.path.exists(md_file)
    assert os.path.exists(html_file)
    assert os.path.exists(json_file)

    with open(md_file, "r", encoding="utf-8") as f:
        md_text = f.read()
        assert "真实量价预测研报" in md_text

def test_backtester():
    feed = FuturesDataFeed()
    klines = feed.get_historical_klines("CJ2701", days=40)
    backtester = QuantitativeBacktester(initial_capital=500000.0)
    result = backtester.run_backtest(klines)

    assert result.total_trades >= 0
    assert 0.0 <= result.win_rate <= 100.0
