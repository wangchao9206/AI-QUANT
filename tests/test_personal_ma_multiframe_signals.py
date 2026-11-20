from datetime import date, datetime, time, timedelta

import pytest

from backtesting import personal_ma_multiframe_signals as signals
from data.data_feed import KLineBar
from data.trading_day import SHANGHAI


def native_tape(start, count):
    return [KLineBar(start + timedelta(minutes=15 * i), 101 + i, 104 + i, 100 + i, 102 + i,
                     10 * (i + 1), 20 + i, 'SC2609') for i in range(count)]


def test_overnight_buckets_keep_exchange_date_and_drop_incomplete_interval():
    friday_open = datetime(2026, 6, 5, 21, tzinfo=SHANGHAI)
    monday = date(2026, 6, 8)
    native = native_tape(friday_open, 22)
    native.pop(9)
    result = signals.minute_events(native, [monday] * len(native), {'night': [('21:00', '26:30')]}, 15)
    bar_ends = list(result[60]['scoringDaysByTime'])
    assert bar_ends == [friday_open + timedelta(hours=hour) for hour in (1, 2, 4, 5)]
    assert set(result[60]['scoringDaysByTime'].values()) == {monday}
    assert result[60]['buckets'][0] == KLineBar(bar_ends[0], 101, 107, 100, 105, 100, 23, 'SC2609')
    assert len(result[15]['buckets']) == 21
    ordinary_clocks = signals.minute_events(native, [monday] * len(native), [(time(21), time(2, 30))], 15)
    assert ordinary_clocks == result


def test_family_events_use_confirmation_end_and_or_retains_each_direction(monkeypatch):
    stamp = datetime(2026, 6, 8, 9, tzinfo=SHANGHAI)
    native = native_tape(stamp, 4)

    def events(bars, family):
        side = 1 if family == 'CHAN_PEN_T3' else -1
        return {'events': [{'direction': side, 'pivotIndex': 0, 'confirmedIndex': 1}] if len(bars) >= 2 else []}

    monkeypatch.setattr(signals, 'detect', events)
    monkeypatch.setattr(signals, '_wyckoff_confirmations', lambda bars, candidates: candidates)
    session = [('09:00', '10:00')]
    result = signals.minute_events(native, [stamp.date()] * 4, session, 15, periods=(30,))[30]
    confirmed = stamp + timedelta(hours=1)
    assert result['chan'] == {confirmed: 1}
    assert result['wyckoff'] == {confirmed: -1}
    assert result['either'] == {confirmed: (-1, 1)}
    prefix = signals.minute_events(native[:-1], [stamp.date()] * 3, session, 15, periods=(30,))[30]
    assert len(prefix['buckets']) == 1
    assert not prefix['either']


def test_rejects_ambiguous_native_chronology():
    stamp = datetime(2026, 6, 8, 9, tzinfo=SHANGHAI)
    native = native_tape(stamp, 4)
    session = [('09:00', '10:00')]
    with pytest.raises(ValueError, match='chronology'):
        signals.minute_events([native[0], native[0]], [stamp.date()] * 2, session, 15)
    with pytest.raises(ValueError, match='overlaps'):
        signals.minute_events(native, [stamp.date()] * 4, session * 2, 15)
