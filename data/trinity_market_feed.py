"""Completed, session-aligned bars for three-in-one paper execution."""

from bisect import bisect_left
from datetime import datetime, timedelta

from data.trading_day import SHANGHAI


NATIVE_BAR = timedelta(minutes=15)
MIN_COMPLETE_DAYS = 20


def _clock_offset(clock):
    parts = clock.split(':')
    if len(parts) not in (2, 3):
        raise ValueError('Invalid exchange clock')
    hour, minute = map(int, parts[:2])
    seconds = int(parts[2]) if len(parts) == 3 else 0
    if not 0 <= hour < 48 or not 0 <= minute < 60 or seconds:
        raise ValueError('Exchange clock is not minute-aligned')
    return timedelta(hours=hour, minutes=minute)


def _session_ranges(sessions):
    result = []
    for first, last in sessions:
        start, end = _clock_offset(first), _clock_offset(last)
        if end < start:
            end += timedelta(days=1)
        if not timedelta() < end - start < timedelta(days=1) or start >= timedelta(days=1):
            raise ValueError('Invalid exchange session')
        result.append((start, end))
    return result


def _session_slots(day, previous_day, day_ranges, night_ranges):
    ranges = [(day, start, end) for start, end in day_ranges]
    if previous_day:
        gap = (day - previous_day).days
        if gap == 1 or gap == 3 and previous_day.weekday() == 4:
            ranges.extend((previous_day, start, end) for start, end in night_ranges)
    slots = []
    for anchor, start, end in ranges:
        midnight = datetime.combine(anchor, datetime.min.time(), SHANGHAI)
        cursor, closing = midnight + start, midnight + end
        while cursor < closing:
            slots.append((cursor, min(cursor + NATIVE_BAR, closing)))
            cursor += NATIVE_BAR
    slots.sort()
    if any(first[1] > second[0] for first, second in zip(slots, slots[1:])):
        raise ValueError('Overlapping exchange sessions')
    return slots


def _market_bar(row, contract):
    return {**{key: row[key] for key in ('timestamp', 'open', 'high', 'low', 'close', 'volume')},
            'contract': contract, 'openInterest': row.get('openInterest', 0)}


def _minute_history(minutes, daily, calendar, index, sessions, quote_at, contract):
    """Check the most recent contiguous suffix against session slots and daily OHLCV."""
    day_ranges = _session_ranges(sessions.get('day', []))
    night_ranges = _session_ranges(sessions.get('night', []))
    if not day_ranges or not minutes:
        raise ValueError('等待真实日内行情及交易时段')
    observed = {datetime.fromisoformat(row['timestamp']): row for row in minutes}
    current_slots = _session_slots(calendar[index], calendar[index - 1], day_ranges, night_ranges)
    active = next((start for start, end in current_slots if start <= quote_at < end), None)
    if active is None or max(observed) != active:
        raise ValueError('15 分钟行情尚未与最新报价同步')
    current = [(start, end) for start, end in current_slots if end <= active]
    if any(start not in observed for start, _ in current):
        raise ValueError('本交易日的 15 分钟行情有缺口')
    groups = [(calendar[index], current)]

    for previous in range(index - 1, 0, -1):
        trading_date = calendar[previous]
        if trading_date not in daily:
            break
        slots = _session_slots(trading_date, calendar[previous - 1], day_ranges, night_ranges)
        if any(start not in observed for start, _ in slots):
            break
        rows = [observed[start] for start, _ in slots]
        aggregate = (rows[0]['open'], max(row['high'] for row in rows), min(row['low'] for row in rows),
                     rows[-1]['close'], sum(row['volume'] for row in rows))
        if aggregate != tuple(daily[trading_date][key] for key in ('open', 'high', 'low', 'close', 'volume')):
            break
        groups.append((trading_date, slots))

    if len(groups) - 1 < MIN_COMPLETE_DAYS:
        raise ValueError('需要至少 20 个连续完整交易日的 15 分钟行情')
    all_slots = {start for _, slots in groups for start, _ in slots}
    actual = {stamp for stamp in observed if min(all_slots) <= stamp < active}
    if actual != all_slots:
        raise ValueError('15 分钟行情与交易时段不一致')
    # Session tails shorter than 15m can verify the daily ledger, but never feed a full-period signal.
    pairs = [(day, _market_bar(observed[start], contract)) for day, slots in reversed(groups)
             for start, end in slots if end - start == NATIVE_BAR]
    return [row for _, row in pairs], [day.isoformat() for day, _ in pairs]


def snapshot(feed, contract):
    from data.tqsdk_feed import canonical_symbol

    provider = feed.provider_symbol(contract)
    if not provider or canonical_symbol(provider) != contract:
        raise ValueError('实际合约不在天勤主行情目录中')
    feed.intraday.request_trinity(contract)
    feed.wake_event.set()
    execution = feed.execution_snapshot(contract)
    quote = execution['quote'] or {}
    if (execution['contract'] != contract or execution['marketState'] != 'LIVE'
            or quote.get('dataStatus') != 'FRESH'):
        raise ValueError('等待实际合约开市及新鲜主源报价')
    checked_at = datetime.fromisoformat(execution['checkedAt'])
    quote_at = datetime.fromisoformat(quote['dataTimestamp'])
    if not timedelta() <= checked_at - quote_at <= timedelta(seconds=feed.freshness_seconds):
        raise ValueError('实际合约报价时间无效或已过期')
    sessions = quote.get('tradingSessions', {})
    trading_date = execution['tradingDate']
    with feed.lock:
        calendar = feed.trading_dates
    if not trading_date:
        raise ValueError('实际合约交易日历未就绪')
    index = bisect_left(calendar, trading_date)
    if not 1 <= index < len(calendar) or calendar[index] != trading_date:
        raise ValueError('实际合约交易日未在主源日历中确认')
    daily_series, minutes = feed.intraday.trinity_series(contract)
    daily = {datetime.fromisoformat(row['timestamp']).astimezone(SHANGHAI).date(): row
             for row in daily_series}
    if len(daily) != len(daily_series) or not daily or max(daily) != trading_date:
        raise ValueError('等待日线更新至当前交易日')
    daily_bars = []
    for day in reversed(calendar[:index]):
        if day not in daily:
            break
        daily_bars.append(_market_bar(daily[day], contract))
    if not daily_bars:
        raise ValueError('上一交易日的已完成日线缺失')
    try:
        minute_bars, minute_dates = _minute_history(minutes, daily, calendar, index, sessions, quote_at, contract)
        minute_status = 'READY'
    except (ValueError, TypeError, AttributeError) as error:
        # Daily exits can still be decided while minute entries wait for valid data.
        minute_bars, minute_dates = [], []
        minute_status = str(error)
    return {'contract': contract, 'asOf': checked_at.isoformat(), 'dailyBars': daily_bars[::-1],
            'minuteBars': minute_bars, 'minuteTradingDates': minute_dates, 'minuteCadence': 15,
            'tradingSessions': sessions, 'tradingDate': trading_date.isoformat(), 'minuteStatus': minute_status}
