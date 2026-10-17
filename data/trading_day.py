"""Daily-bar boundaries use exchange trading dates, not quote calendar dates."""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from data.data_feed import KLineBar, MarketQuote

SHANGHAI = ZoneInfo('Asia/Shanghai')


def completed_daily_bar(timestamp: datetime, now: datetime | None = None) -> bool:
    now = (now or datetime.now(SHANGHAI)).astimezone(SHANGHAI)
    day = timestamp.astimezone(SHANGHAI).date()
    # All supported Chinese futures day sessions have ended by 16:00.
    return day < now.date() or (day == now.date() and now.time() >= time(16))


def merge_daily_quote(bars: list[KLineBar], quote: MarketQuote,
                      trading_date: date | None = None) -> list[KLineBar]:
    observed = quote.timestamp.astimezone(SHANGHAI)
    byday = {b.timestamp.astimezone(SHANGHAI).date(): b for b in sorted(bars, key=lambda b: b.timestamp)}
    if trading_date is None:
        if 6 <= observed.hour < 18:
            trading_date = observed.date()
        else:
            earliest = observed.date() + timedelta(days=observed.hour >= 18)
            # An upstream daily bar is an observed trading-calendar label,
            # including weekends and holidays. Do not invent a night date
            # when neither the exchange calendar nor daily bar is available.
            trading_date = next((d for d in sorted(byday) if earliest <= d <= earliest + timedelta(days=14)), None)
    if trading_date is None or quote.volume <= 0:
        return [byday[d] for d in sorted(byday)]
    existing = byday.get(trading_date)
    if existing is not None and quote.volume < existing.volume:
        return [byday[d] for d in sorted(byday)]
    live = KLineBar(datetime.combine(trading_date, time(), SHANGHAI),
                    quote.open, quote.high, quote.low, quote.price,
                    quote.volume, quote.open_interest,
                    existing.contract_symbol if existing else None)
    byday[trading_date] = live
    return [byday[d] for d in sorted(byday)]
