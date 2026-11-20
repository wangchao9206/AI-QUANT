"""Complete session buckets and causal minute entry signals for one delivery contract."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from datetime import date, datetime, time, timedelta
from math import isfinite

from backtesting.chanlun_research import detect
from backtesting.personal_ma_overlay import _by_confirmation, _wyckoff_confirmations
from data.data_feed import KLineBar
from data.trading_day import SHANGHAI


PERIODS = (15, 30, 60)
DAY = timedelta(days=1)


def _clock_offset(value: time | str) -> timedelta:
    if isinstance(value, time):
        if value.tzinfo is not None or value.second or value.microsecond:
            raise ValueError('Use local minute-aligned session clocks')
        return timedelta(hours=value.hour, minutes=value.minute)
    parts = value.split(':')
    if len(parts) not in (2, 3) or not all(part.isdecimal() for part in parts):
        raise ValueError(f'Invalid session clock {value!r}')
    hour, minute = (int(part) for part in parts[:2])
    if hour >= 48 or minute >= 60 or (len(parts) == 3 and int(parts[2]) != 0):
        raise ValueError(f'Invalid session clock {value!r}')
    return timedelta(hours=hour, minutes=minute)


def _session_offsets(sessions):
    if isinstance(sessions, Mapping):
        sessions = (*sessions.get('day', ()), *sessions.get('night', ()))
    result = []
    for first, last in sessions:
        start, end = _clock_offset(first), _clock_offset(last)
        if start >= DAY or start == end:
            raise ValueError('Session has an invalid start or duration')
        if end < start:
            end += DAY
        if end - start >= DAY:
            raise ValueError('A session must be shorter than 24 hours')
        result.append((start, end))
    if not result:
        raise ValueError('At least one session is required')
    return result


def _session_bounds(stamp, offsets):
    local = stamp.astimezone(SHANGHAI)
    midnight = datetime.combine(local.date(), time(), SHANGHAI)
    candidates = []
    for start, end in offsets:
        for anchor in (midnight - DAY, midnight):
            opening, closing = anchor + start, anchor + end
            if opening <= local < closing:
                candidates.append((local, opening, closing))
    if len(candidates) != 1:
        raise ValueError(f'Minute is outside or overlaps exchange sessions: {local.isoformat()}')
    return candidates[0]


def _native_sessions(native_bars, trading_days, sessions, step):
    offsets = _session_offsets(sessions)
    contract = native_bars[0].contract_symbol if native_bars else None
    previous_stamp = previous_day = None
    for bar, trade_day in zip(native_bars, trading_days):
        stamp = bar.timestamp
        if (stamp.tzinfo is None or bar.contract_symbol != contract or not contract
                or not isinstance(trade_day, date) or isinstance(trade_day, datetime)):
            raise ValueError('Expected a single delivery contract, aware clock and exchange date')
        if previous_stamp is not None and (stamp <= previous_stamp or trade_day < previous_day):
            raise ValueError('Minute and exchange date chronology must be ordered')
        if (not all(isfinite(value) for value in (bar.open, bar.high, bar.low, bar.close, bar.volume))
                or not 0 < bar.low <= min(bar.open, bar.close) <= max(bar.open, bar.close) <= bar.high
                or bar.volume < 0):
            raise ValueError('Invalid minute OHLC or volume')
        local, opening, closing = _session_bounds(stamp, offsets)
        if (local - opening) % step or local + step > closing:
            raise ValueError(f'Native minute does not align with its session: {local.isoformat()}')
        yield bar, trade_day, local, opening, closing
        previous_stamp, previous_day = stamp, trade_day


def _aggregate(period, rows, step):
    interval = timedelta(minutes=period)
    expected_count = interval // step
    groups = defaultdict(list)
    for bar, trade_day, local, opening, closing in rows:
        start = opening + ((local - opening) // interval) * interval
        if start + interval <= closing:
            groups[start, trade_day].append((local, bar))

    buckets, days_by_time = [], {}
    for (start, trade_day), values in sorted(groups.items()):
        if (len(values) != expected_count
                or any(stamp != start + i * step for i, (stamp, _) in enumerate(values))):
            continue
        bars = [bar for _, bar in values]
        first, last = bars[0], bars[-1]
        end = start + interval
        if end in days_by_time:
            raise ValueError('Ambiguous exchange date for a completed signal bucket')
        buckets.append(KLineBar(end, first.open, max(bar.high for bar in bars),
                                min(bar.low for bar in bars), last.close,
                                sum(bar.volume for bar in bars), last.open_interest,
                                first.contract_symbol))
        days_by_time[end] = trade_day
    return buckets, days_by_time


def _signal_directions(bars, events):
    return {bars[index].timestamp: event['direction']
            for index, event in _by_confirmation(events).items()}


def minute_events(native_bars, trading_days, sessions, native_minutes, periods=PERIODS) -> dict[int, dict]:
    """Return fresh bilateral Chan and Wyckoff events at their completed K-line times.

    Input bars have native opening timestamps and aligned exchange trading dates.
    Buckets end at the first instant at which all their input bars are complete.
    Session tails and buckets with missing native bars are dropped. No resampling
    crosses a break or changes a provider trading date. OR accepts either event at
    the current bucket close and keeps both directions when they disagree, so the
    already-known daily direction determines which side can be traded.
    """
    periods = tuple(periods)
    if (len(native_bars) != len(trading_days) or not isinstance(native_minutes, int)
            or isinstance(native_minutes, bool) or native_minutes < 1 or not periods
            or len(set(periods)) != len(periods)
            or any(period not in PERIODS or period % native_minutes for period in periods)):
        raise ValueError('Invalid period, native cadence or trading-date alignment')
    step = timedelta(minutes=native_minutes)
    rows = list(_native_sessions(native_bars, trading_days, sessions, step))
    result = {}
    for period in periods:
        buckets, days_by_time = _aggregate(period, rows, step)
        chan = _signal_directions(buckets, detect(buckets, 'CHAN_PEN_T3')['events'])
        retests = detect(buckets, 'RANGE_RETEST')['events']
        wyckoff = _signal_directions(buckets, _wyckoff_confirmations(buckets, retests))
        either = {stamp: tuple(sorted({source[stamp] for source in (chan, wyckoff) if stamp in source}))
                  for stamp in sorted(chan.keys() | wyckoff.keys())}
        result[period] = {'chan': chan, 'wyckoff': wyckoff, 'either': either,
                          'scoringDaysByTime': days_by_time, 'buckets': buckets}
    return result
