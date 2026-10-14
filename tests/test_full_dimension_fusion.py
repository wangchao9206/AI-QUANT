from datetime import datetime, timedelta, timezone

from data.data_feed import KLineBar, MarketQuote
from data.evidence_feed import EvidenceBatch, SHANGHAI_TZ
from engines.fusion_engine import HolisticFusionEngine


def _context():
    observed = datetime(2026, 10, 14, 10, 30, tzinfo=SHANGHAI_TZ)
    bars = []
    for index in range(45):
        close = 10000 + index * 12 + (index % 4) * 8
        bars.append(KLineBar(
            timestamp=observed - timedelta(days=44-index),
            open=close - 15,
            high=close + 55,
            low=close - 48,
            close=close,
            volume=15000 + index * 120,
            open_interest=50000 + index * 180,
        ))
    quote = MarketQuote(
        symbol="CJ2701", name="红枣2701", price=10550, change=80, change_pct=0.76,
        open=10480, high=10620, low=10420, prev_close=10470, prev_settlement=10470,
        volume=24000, turnover=250000000, open_interest=59000,
        timestamp=observed, is_live=True,
    )
    curve = {
        code: MarketQuote(
            symbol=code, name=code, price=price, change=10, change_pct=.1,
            open=price-10, high=price+40, low=price-40, prev_close=price-10,
            prev_settlement=price-10, volume=5000, turnover=50000000,
            open_interest=0, timestamp=observed, is_live=True,
        )
        for code, price in {"CJ612": 10300, "CJ701": 10420, "CJ703": 10500, "CJ705": 10580}.items()
    }
    weather = EvidenceBatch("weather", "Open-Meteo", "https://open-meteo.com", observed, [
        {"region": region, "date": "2026-10-14", "temperature_max": 22, "temperature_min": 8, "precipitation": 1.2, "humidity": 48}
        for region in ("若羌", "阿克苏", "喀什")
    ])
    news = EvidenceBatch("news", "东方财富", "https://eastmoney.com", observed, [
        {"title": "红枣期价走强", "summary": "产区惜售", "observed_at": observed}
    ])
    rules = EvidenceBatch("trading_rules", "东方财富", "https://eastmoney.com", observed, [
        {"contract": "CJ701", "price_limit_pct": 7.0, "margin_pct": 17.0}
    ])
    return {
        "symbol": "CJ2701", "quote": quote, "klines": bars,
        "term_structure": curve, "weather": weather, "news": news,
        "trading_rules": rules, "analysis_time": observed,
    }


def test_eleven_empirical_dimensions_and_three_isolated_references():
    decision = HolisticFusionEngine().evaluate_all(_context())

    assert set(decision.dimension_results) == {
        "weather", "momentum", "indicators", "sentiment", "supply_demand",
        "policy", "positioning", "execution", "spread", "term_structure", "liquidity",
    }
    assert len(decision.dimension_results) == 11
    assert all(item.category == "EMPIRICAL" for item in decision.dimension_results.values())
    assert all(item.included_in_score for item in decision.dimension_results.values())
    assert all(item.score is not None for item in decision.dimension_results.values())
    assert set(decision.cultural_references) == {"liuyao", "iching", "qimen"}
    for item in decision.cultural_references.values():
        assert item.category == "CULTURAL_REFERENCE"
        assert item.data_status == "REFERENCE"
        assert item.score is None
        assert item.confidence is None
        assert item.weight == 0
        assert item.included_in_score is False


def test_missing_optional_evidence_is_explicitly_unavailable():
    context = _context()
    del context["weather"]
    decision = HolisticFusionEngine().evaluate_all(context)

    weather = decision.dimension_results["weather"]
    assert weather.data_status == "UNAVAILABLE"
    assert weather.score is None
    assert weather.included_in_score is False
