from datetime import datetime, timedelta, timezone

import pytest

from data.data_feed import KLineBar, MarketQuote


@pytest.fixture
def market_context():
    """Stable observed-shaped inputs; unit tests must not depend on public API uptime."""
    observed = datetime(2026, 10, 15, 3, 29, 59, tzinfo=timezone.utc)
    bars = []
    for index in range(45):
        close = 6200 + index * 7 + (index % 5) * 4
        bars.append(KLineBar(
            timestamp=observed - timedelta(days=44 - index),
            open=close - 12,
            high=close + 35,
            low=close - 30,
            close=close,
            volume=18000 + index * 250,
            open_interest=210000 + index * 500,
        ))
    quote = MarketQuote(
        symbol="CJ2701",
        name="红枣2701",
        price=6530,
        change=45,
        change_pct=0.69,
        open=6385,
        high=6565,
        low=6370,
        prev_close=6485,
        prev_settlement=6485,
        volume=286188,
        turnover=0,
        open_interest=236173,
        timestamp=observed,
        is_live=True,
    )
    return {"symbol": "CJ2701", "quote": quote, "klines": bars}
