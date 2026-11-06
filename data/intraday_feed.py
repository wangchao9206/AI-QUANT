"""Primary-only small-period bars; every SDK operation runs on the feed worker."""
from __future__ import annotations

import copy
import math
import threading
import time
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

PERIODS = (15, 30, 60, 180, 300, 900)
CALENDAR_PERIODS = ('DAY', 'WEEK', 'MONTH')
SHANGHAI = ZoneInfo('Asia/Shanghai')


def period_key(period):
    if period in CALENDAR_PERIODS:
        return period
    if isinstance(period, int) and period in PERIODS:
        return str(period)
    raise ValueError('Unsupported chart period')


def calendar_bars(daily, period, complete_start=False):
    """Aggregate observed provider trading-date labels, never fixed 7/30-day spans."""
    groups = {}
    for bar in daily:
        day = datetime.fromisoformat(bar['timestamp']).astimezone(SHANGHAI).date()
        start = day - timedelta(days=day.weekday()) if period == 'WEEK' else day.replace(day=1)
        if start not in groups:
            groups[start] = {**bar, 'timestamp': datetime.combine(start, datetime.min.time(), SHANGHAI).isoformat(),
                             'firstTradingDate': day.isoformat(), 'lastTradingDate': day.isoformat()}
        else:
            item = groups[start]
            item.update(high=max(item['high'], bar['high']), low=min(item['low'], bar['low']),
                        price=bar['price'], volume=item['volume'] + bar['volume'], lastTradingDate=day.isoformat())
            item.pop('openInterest', None)
            if 'openInterest' in bar:
                item['openInterest'] = bar['openInterest']
    result = list(groups.values())
    if not complete_start:
        result = result[1:]  # The source window may begin midway through this bucket.
    for i, bar in enumerate(result):
        bar['changePctKnown'] = i > 0
        bar['changePct'] = (bar['price'] / result[i-1]['price'] - 1)*100 if i else 0
    return result


def finite(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def observed_bars(serial):
    records = serial.to_dict('records') if hasattr(serial, 'to_dict') else list(serial)
    bars = {}
    for row in records:
        if finite(row.get('id')) is not None and float(row['id']) < 0:
            continue
        stamp = finite(row.get('datetime'))
        values = [finite(row.get(k)) for k in ('open', 'high', 'low', 'close', 'volume')]
        if stamp is None or stamp <= 0 or any(v is None for v in values):
            continue
        opening, high, low, close, volume = values
        if min(opening, high, low, close) <= 0 or volume < 0 or low > min(opening, close) or high < max(opening, close):
            continue
        try:
            timestamp = datetime.fromtimestamp(stamp / 1e9, timezone.utc).isoformat()
        except (ValueError, OverflowError, OSError):
            continue
        bar = dict(timestamp=timestamp, open=opening, high=high, low=low, price=close,
                   volume=int(volume), changePct=0, changePctKnown=False)
        oi = finite(row.get('close_oi'))
        if oi is not None and oi >= 0:
            bar['openInterest'] = int(oi)
        bars[timestamp] = bar
    result = [bars[k] for k in sorted(bars)]
    for previous, current in zip(result, result[1:]):
        current['changePct'] = (current['price'] / previous['price'] - 1) * 100
        current['changePctKnown'] = True
    return result


class IntradayFeedState:
    MAX_SUBSCRIPTIONS = 48

    def __init__(self):
        self.lock = threading.RLock()
        self.requested = set()
        self.snapshots = {}
        self.errors = {}
        self.entities = {}
        self.retry = {}

    def request(self, symbol, seconds, providers):
        period = period_key(seconds)
        if symbol not in providers:
            raise ValueError('合约不在天勤实际目录中，请刷新目录后选择。')
        key = (symbol, period)
        with self.lock:
            if key not in self.requested and len(self.requested) >= self.MAX_SUBSCRIPTIONS:
                raise ValueError('看盘订阅已达到 48 组上限，请复用已有合约周期。')
            self.requested.add(key)
        return key

    def reset_session(self):
        self.entities.clear()
        self.retry.clear()

    def _capture(self, key, serial):
        bars = observed_bars(serial.copy())
        captured = {key: bars}
        if key[1] == 'DAY' and bars:
            records = serial.to_dict('records') if hasattr(serial, 'to_dict') else list(serial)
            valid = [r for r in records if finite(r.get('id')) is not None and r['id'] >= 0]
            if len(valid) != len(bars) or any(r['id'] != int(r['id']) for r in valid) or any(
                    b['id'] != a['id']+1 or b['datetime'] <= a['datetime'] for a,b in zip(valid,valid[1:])):
                raise ValueError('Incomplete observed daily serial')
            complete = bool(valid and valid[0]['id'] == 0)
            captured.update({(key[0], p): calendar_bars(bars, p, complete) for p in ('WEEK', 'MONTH')})
        with self.lock:
            for target, points in captured.items():
                if points:
                    self.snapshots[target] = dict(points=points[-600:], receivedAt=datetime.now(timezone.utc).isoformat())
                    self.errors.pop(target, None)

    def subscribe_pending(self, api, providers):
        with self.lock:
            wanted = {(s, 'DAY' if p in CALENDAR_PERIODS else p) for s, p in self.requested}
            pending = sorted(wanted - self.entities.keys())
        for key in pending:
            if key[0] not in providers or time.monotonic() < self.retry.get(key, 0):
                continue
            try:
                serial = api.get_kline_serial(providers[key[0]], 86400 if key[1] == 'DAY' else int(key[1]),
                                             data_length=8000 if key[1] == 'DAY' else 600)
                self.entities[key] = serial
                self._capture(key, serial)
            except Exception:
                self.entities.pop(key, None)
                self.retry[key] = time.monotonic() + 30
                with self.lock:
                    self.errors[key] = '天勤 K 线订阅暂不可用，正在重试。'
            break  # Avoid draining many synchronous subscriptions in one worker cycle.

    def update(self, api):
        for key, serial in list(self.entities.items()):
            if api.is_changing(serial):
                try:
                    self._capture(key, serial)
                except (ValueError, TypeError, OverflowError):
                    with self.lock:
                        self.errors[key] = '行情序列校验失败，保留上次快照并等待有效数据。'

    def snapshot(self, key, quote, connected, freshness, limit=400, now=None):
        now = now or datetime.now(timezone.utc)
        with self.lock:
            result = copy.deepcopy(self.snapshots.get(key))
            error = self.errors.get(key)
            if key[1] in CALENDAR_PERIODS:
                error = error or self.errors.get((key[0], 'DAY'))
        if not result:
            raise ValueError(error or '正在订阅真实 K 线，请稍后重试。')
        stamp = quote.get('dataTimestamp') if quote else None
        fresh = False
        if stamp:
            observed = datetime.fromisoformat(stamp)
            bar_start = datetime.fromisoformat(result['points'][-1]['timestamp'])
            age = (now - observed).total_seconds()
            if key[1] in CALENDAR_PERIODS:
                # Long bars use trading dates, including the following day's night session.
                last_day = result['points'][-1].get('lastTradingDate', bar_start.astimezone(SHANGHAI).date().isoformat())
                local = observed.astimezone(SHANGHAI)
                trading_day = quote.get('tradingDate')
                if not trading_day and 6 <= local.hour < 18:
                    trading_day = local.date().isoformat()
                current = trading_day == last_day
            else:
                current = 0 <= (observed - bar_start).total_seconds() <= int(key[1])
            fresh = connected and not error and 0 <= age <= freshness and current
        return {**result, 'symbol': key[0], 'period': key[1],
                'seconds': 86400 if key[1] == 'DAY' else 0 if key[1] in CALENDAR_PERIODS else int(key[1]),
                'source': '天勤 TqSdk 日线汇总' if key[1] in ('WEEK', 'MONTH') else '天勤 TqSdk K 线',
                'dataStatus': 'FRESH' if fresh else 'CACHED', 'dataTimestamp': stamp,
                'connected': connected, 'retrievedAt': now.isoformat(), 'message': error or '',
                'points': result['points'][-max(1, min(600, limit)):],
                'lastBarProvisional': True}
