from datetime import date, datetime

import pytest

from data.data_feed import KLineBar, MarketQuote
from data.live_feed import SHANGHAI
from data.trading_day import completed_daily_bar, merge_daily_quote
from data.tqsdk_feed import TqSdkRealtimeFeed


def bar(day, volume=100):
    return KLineBar(datetime.fromisoformat(day + 'T00:00:00+08:00'),
                    100, 110, 90, 105, volume, 1000)


def quote(ts):
    return MarketQuote('RBM', 'RBM', 106, 1, 1, 100, 110, 90, 105, 105,
                       200, 0, 1000, datetime.fromisoformat(ts))


@pytest.mark.parametrize('ts', ['2026-10-16T23:00:00+08:00', '2026-10-17T02:30:00+08:00'])
def test_friday_night_replaces_monday_bar_without_duplicate_or_time_reversal(ts):
    original = [bar('2026-10-16'), bar('2026-10-19')]
    merged = merge_daily_quote(original, quote(ts))
    assert len(merged) == 2
    assert [b.timestamp.date() for b in merged] == [date(2026, 10, 16), date(2026, 10, 19)]
    assert merged[-1].close == 106
    assert original[-1].close == 105


def test_calendar_supplies_night_day_before_upstream_bar_arrives():
    feed = TqSdkRealtimeFeed()
    feed.trading_dates = (date(2026, 10, 16), date(2026, 10, 19))
    q = quote('2026-10-16T23:00:00+08:00')
    day = feed.trading_date_for(q.timestamp)
    merged = merge_daily_quote([bar('2026-10-16')], q, day)
    assert merged[-1].timestamp.date() == date(2026, 10, 19)


def test_night_date_is_not_guessed_without_calendar_or_observed_bar():
    original = [bar('2026-10-16')]
    assert merge_daily_quote(original, quote('2026-10-16T23:00:00+08:00')) == original


def test_stale_quote_does_not_replace_higher_volume_daily_bar():
    original = [bar('2026-10-19', volume=500)]
    assert merge_daily_quote(original, quote('2026-10-16T23:00:00+08:00')) == original


@pytest.mark.parametrize('ts,now,expected', [
    ('2026-10-19T00:00:00+08:00', '2026-10-17T12:00:00+08:00', False),
    ('2026-10-16T00:00:00+08:00', '2026-10-16T14:00:00+08:00', False),
    ('2026-10-16T00:00:00+08:00', '2026-10-16T16:00:00+08:00', True),
])
def test_only_finished_daily_bars_are_eligible(ts, now, expected):
    assert completed_daily_bar(datetime.fromisoformat(ts), datetime.fromisoformat(now)) is expected
