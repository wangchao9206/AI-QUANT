"""Primary-provider only, conservative sealed-bar snapshots for Chan monitors."""
import copy
import math
from datetime import datetime, timedelta, timezone

from data.live_feed import SHANGHAI

FREQUENCIES = {'DAY': 86400, 'MIN5': 300, 'MIN30': 1800}


def serial_bars(serial):
    rows = serial.to_dict('records') if hasattr(serial, 'to_dict') else list(serial)
    result = []
    for row in rows:
        index = float(row.get('id', -1))
        if not math.isfinite(index) or index < 0:
            continue  # SDK leading padding, not a market candle.
        if index != int(index):
            raise ValueError('Nonintegral provider serial index')
        stamp = datetime.fromtimestamp(int(row['datetime']) / 1_000_000_000, SHANGHAI)
        values = {k: float(row[k]) for k in ('open', 'high', 'low', 'close')}
        if not all(math.isfinite(v) and v > 0 for v in values.values()):
            raise ValueError('Invalid observed provider candle')
        if not values['low'] <= min(values['open'], values['close']) <= max(values['open'], values['close']) <= values['high']:
            raise ValueError('Invalid provider OHLC envelope')
        volume = float(row['volume'])
        if not math.isfinite(volume) or volume < 0 or volume != int(volume):
            raise ValueError('Invalid provider volume')
        bar = {'providerIndex': int(index), 'timestamp': stamp.isoformat(), 'date': stamp.date().isoformat(),
               'volume': int(volume), **values}
        if result and (bar['providerIndex'] != result[-1]['providerIndex'] + 1 or bar['timestamp'] <= result[-1]['timestamp']):
            raise ValueError('Noncontiguous provider sequence')
        result.append(bar)
    return result


def sealed_bars(bars, frequency, now):
    """The last provider bar remains pending, even after a session closes."""
    seconds = FREQUENCIES[frequency]
    if frequency == 'DAY':
        # Preserve the provider's daily timestamp; do not infer a trading date or
        # a midnight/16:00 availability time from it. A successor is required.
        return [a for a,b in zip(bars,bars[1:]) if datetime.fromisoformat(b['timestamp'])<=now]
    return [a for a, b in zip(bars, bars[1:])
            if datetime.fromisoformat(b['timestamp']) >= datetime.fromisoformat(a['timestamp']) + timedelta(seconds=seconds)
            and datetime.fromisoformat(b['timestamp']) <= now]


def session_open(now, dates, sessions):
    local = now.astimezone(SHANGHAI)
    if not dates or not dates[0] <= local.date() <= dates[-1] or not any(sessions.values()):
        return None
    def within(base, intervals):
        for start, end in intervals:
            def at(text):
                h, m, s = map(int, text.split(':'))
                return datetime.combine(base, datetime.min.time(), SHANGHAI)+timedelta(hours=h,minutes=m,seconds=s)
            if at(start) <= local < at(end):
                return True
        return False
    if local.date() in dates and within(local.date(), sessions.get('day', [])):
        return True
    base = local.date()-timedelta(days=local.hour<6)
    following = next((d for d in dates if d>base), None)
    gap = (following-base).days if following else 0
    permitted = base in dates and (gap==1 or (gap==3 and base.weekday()==4))
    return bool(permitted and within(base, sessions.get('night', [])))


def primary_snapshot(feed, symbol, frequency, now=None):
    now = now or datetime.now(timezone.utc)
    key = (symbol, FREQUENCIES[frequency])
    feed.watch_chanlun(symbol, key[1])
    with feed.lock:
        connected, pump = feed.connected, feed.chanlun_pump_at
        source = copy.deepcopy(feed.chanlun_snapshots.get(key))
        error = feed.chanlun_errors.get(key)
        provider = feed.provider_symbols.get(symbol)
        quote = copy.deepcopy(feed.quotes.get(symbol))
        specs = copy.deepcopy(feed.execution_specs.get(symbol, {}))
        dates = tuple(feed.trading_dates)
    base = {'symbol': symbol, 'frequency': frequency, 'providerSymbol': provider,
            'source': 'TQSDK_PRIMARY_SERIAL', 'priceBasis': 'UNADJUSTED_DELIVERY',
            'checkedAt': now.isoformat(), 'pumpAt': pump, 'bars': [], 'executable': False,
            'closeProof': 'SUCCESSOR_OBSERVED',
            'timeSemantics': 'OBSERVED_RECEIPT_NOT_HISTORICAL_AVAILABILITY'}
    if not connected:
        return {**base, 'status': 'DISCONNECTED', 'message': '主行情连接断开，暂停新信号'}
    if not pump or (now - datetime.fromisoformat(pump)).total_seconds() > 15:
        return {**base, 'status': 'STALE', 'message': '行情线程心跳过期，暂停新信号'}
    if error:
        return {**base, 'status': 'WAITING_DATA', 'message': '主源订阅或数据校验未通过：'+error}
    if not source:
        return {**base, 'status': 'WAITING_DATA', 'message': '等待主源真实 K 线，不使用公开降级行情'}
    closed = sealed_bars(source['bars'], frequency, now)
    if len(closed) < 50:
        return {**base, 'status': 'WAITING_DATA', 'message': '已封存行情不足 50 根'}
    # A fresh provider pump cannot turn a stale instrument into fresh input.
    # Closed-market bars remain useful, but never generate a fresh inbox alert.
    local = now.astimezone(SHANGHAI)
    if not dates or not dates[0] <= local.date() <= dates[-1]:
        return {**base, 'status': 'STALE', 'message': '交易日历不可用，暂停新信号'}
    latest = datetime.fromisoformat(closed[-1]['timestamp'])
    opened = session_open(now, dates, (quote or specs).get('tradingSessions', {}))
    if opened is None:
        return {**base, 'status': 'STALE', 'message': '合约交易时段未知，暂停新信号'}
    market_closed = not opened
    age = (now-latest).total_seconds()
    quote_at = datetime.fromisoformat(quote['dataTimestamp']) if quote else None
    fresh_quote = quote_at is not None and -5 <= (now-quote_at).total_seconds() <= 60
    # Conservative: lunch/night breaks with stale quotes pause until actual ticks
    # resume; weekends are an explicit closed state rather than fake live data.
    if not market_closed and not fresh_quote:
        return {**base, 'status': 'STALE', 'message': '该合约行情陈旧或休市，等待新鲜主源数据'}
    if not market_closed and frequency != 'DAY' and age > FREQUENCIES[frequency]*3:
        return {**base, 'status': 'STALE', 'message': '分时行情水位落后，暂停新信号'}
    completed = [d for d in dates if d<local.date() or (d==local.date() and local.hour>=16)]
    if frequency!='DAY' and completed and latest.astimezone(SHANGHAI).date()<completed[-1]:
        return {**base, 'status': 'STALE', 'message': '已封存行情落后于交易日历水位'}
    return {**base, 'status': 'CLOSED' if market_closed else 'READY', 'bars': closed,
            'receiptAt': source['receiptAt'], 'latestBarAgeSeconds': age,
            'message': '休市，仅维护历史状态，不发新提醒' if market_closed else '主源已封存行情可用'}
