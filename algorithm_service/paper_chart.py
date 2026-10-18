"""Only completed observations known at the requested paper-trading clock."""
from datetime import datetime, timezone


def visible_bars(bars, as_of: datetime, limit: int):
    if as_of.tzinfo is None:
        raise ValueError('回放时点必须包含时区')
    cutoff = as_of.astimezone(timezone.utc)
    result = []
    for bar in bars:
        stamp = bar.timestamp
        if stamp.tzinfo is None:
            from data.evidence_feed import SHANGHAI_TZ
            stamp = stamp.replace(tzinfo=SHANGHAI_TZ)
        if stamp.astimezone(timezone.utc) <= cutoff:
            result.append({'timestamp': stamp, 'contract': bar.contract_symbol,
                           'open': bar.open, 'high': bar.high, 'low': bar.low,
                           'close': bar.close, 'volume': bar.volume,
                           'openInterest': bar.open_interest})
    return sorted(result, key=lambda row: row['timestamp'])[-limit:]
