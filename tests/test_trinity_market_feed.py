from datetime import date, datetime, time, timedelta
from threading import Event, Lock
from types import SimpleNamespace

import pytest

from data.intraday_feed import IntradayFeedState
from data.trading_day import SHANGHAI
from data.trinity_market_feed import snapshot
from data.tqsdk_feed import quote_to_snapshot


def candle(stamp, volume=1):
    return dict(timestamp=stamp.isoformat(), open=100, high=101, low=99, close=100, volume=volume)


def sample():
    first = date(2026, 10, 12)
    dates = tuple(first + timedelta(days=i) for i in range(36) if (first + timedelta(days=i)).weekday() < 5)
    current = dates[-1]  # Monday trading date; the first quotes arrive on Friday night.
    friday_night = datetime.combine(dates[-2], time(21), SHANGHAI)
    checked_at = friday_night + timedelta(minutes=16)
    sessions = dict(day=[['09:00:00', '10:00:00'], ['13:30:00', '15:00:00']],
                    night=[['21:00:00', '23:00:00']])
    daily, minutes = [], []
    for previous, day in zip(dates, dates[1:-1]):
        openings = [datetime.combine(previous, time(21), SHANGHAI) + timedelta(minutes=15 * i) for i in range(8)]
        openings.extend(datetime.combine(day, time(9), SHANGHAI) + timedelta(minutes=15 * i) for i in range(4))
        openings.extend(datetime.combine(day, time(13, 30), SHANGHAI) + timedelta(minutes=15 * i) for i in range(6))
        minutes.extend(candle(stamp) for stamp in openings)
        daily.append(candle(datetime.combine(day, time(), SHANGHAI), len(openings)))
    minutes.extend(candle(friday_night + timedelta(minutes=step)) for step in (0, 15))
    daily.append(candle(datetime.combine(current, time(), SHANGHAI)))
    context = dict(contract='FG701', marketState='LIVE', checkedAt=checked_at.isoformat(), tradingDate=current,
                   quote=dict(dataStatus='FRESH', dataTimestamp=checked_at.isoformat(), tradingSessions=sessions))
    state = IntradayFeedState()
    state.snapshots[('FG701', 'TRINITY_DAILY')] = dict(points=daily)
    state.snapshots[('FG701', 'TRINITY_MINUTE')] = dict(points=minutes)
    feed = SimpleNamespace(provider_symbol=lambda contract: 'CZCE.FG701', intraday=state,
                           wake_event=Event(), execution_snapshot=lambda contract: context, lock=Lock(),
                           trading_dates=dates, freshness_seconds=15)
    return feed, context, daily, minutes


def test_weekend_night_maps_to_next_trading_day_and_only_completed_bars_are_exposed():
    feed, context, daily, minutes = sample()
    result = snapshot(feed, 'FG701')

    assert result['minuteStatus'] == 'READY'
    assert result['minuteCadence'] == 15
    assert result['minuteTradingDates'][-1] == '2026-11-16'
    assert result['minuteBars'][-1]['timestamp'] == minutes[-2]['timestamp']
    assert result['dailyBars'][-1]['timestamp'] == daily[-2]['timestamp']
    assert all(row['contract'] == 'FG701' for row in result['minuteBars'])
    assert result['asOf'] == context['checkedAt']
    assert feed.wake_event.is_set()


@pytest.mark.parametrize('cause', ('current-gap', 'daily-mismatch', 'stale-minute'))
def test_invalid_minute_history_preserves_daily_exit_data(cause):
    feed, _, daily, minutes = sample()
    if cause == 'current-gap':
        del minutes[-2]
    elif cause == 'daily-mismatch':
        daily[-2]['volume'] += 1
    else:
        minutes.pop()

    result = snapshot(feed, 'FG701')

    assert result['dailyBars']
    assert result['minuteBars'] == result['minuteTradingDates'] == []
    assert result['minuteStatus'] != 'READY'


def test_stale_quote_and_invalid_provider_timestamp_are_rejected():
    feed, context, _, _ = sample()
    context['quote']['dataTimestamp'] = (
        datetime.fromisoformat(context['checkedAt']) - timedelta(minutes=1)
    ).isoformat()
    with pytest.raises(ValueError, match='已过期'):
        snapshot(feed, 'FG701')
    with pytest.raises(ValueError, match='observed timestamp'):
        quote_to_snapshot('FG701', dict(last_price=100, datetime=''))


def test_primary_trinity_history_resets_on_reconnect_without_discarding_chart_cache():
    feed, _, _, _ = sample()
    feed.intraday.request_trinity('FG701')
    feed.intraday.snapshots[('FG701', '900')] = {'points': [1]}

    feed.intraday.reset_session()

    assert feed.intraday.trinity_series('FG701') == ([], [])
    assert feed.intraday.snapshots[('FG701', '900')] == {'points': [1]}
