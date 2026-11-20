"""Close-confirmed signals for the personal SMA5/10/20 research strategy."""

from math import fsum, isfinite


def _sma(closes, period):
    return [None if index + 1 < period else fsum(closes[index + 1 - period:index + 1]) / period
            for index in range(len(closes))]


def _trigger(index, fast, medium, gaps, convergence_days):
    gap = gaps[index]
    previous_gap = gaps[index - 1] if index else None
    if gap is None or previous_gap is None:
        return None
    if gap > 0 >= previous_gap:
        return 'LONG_CROSS'
    if gap < 0 <= previous_gap:
        return 'SHORT_CROSS'
    if gap > 0 and index >= convergence_days and gaps[index - convergence_days] is not None:
        history = gaps[index - convergence_days:index]
        narrowing = previous_gap > 0 and all(older > newer for older, newer in zip(history, history[1:]))
        if narrowing and fast[index - 1] <= medium[index - 1] and fast[index] > medium[index]:
            return 'LONG_REENTRY'
    return None


def ma_tape(bars, *, periods=(5, 10, 20), convergence_days=3):
    """Publish SMA values, regime and action only on each completed daily close."""
    if (len(periods) != 3 or any(type(period) is not int for period in periods)
            or not 2 <= periods[0] < periods[1] < periods[2]
            or type(convergence_days) is not int or convergence_days < 2):
        raise ValueError('Expected increasing SMA periods and at least two convergence days')
    closes = [bar.close for bar in bars]
    if not all(isfinite(close) for close in closes):
        raise ValueError('Daily closes must be finite')
    fast, medium, slow = (_sma(closes, period) for period in periods)
    gaps = [None if last is None else first - last for first, last in zip(fast, slow)]

    tape = []
    for index, gap in enumerate(gaps):
        trend = 0 if gap is None or gap == 0 else 1 if gap > 0 else -1
        strong = 0
        if trend == 1 and closes[index] > fast[index]:
            strong = 1
        elif trend == -1 and closes[index] < fast[index] < fast[index - 1]:
            strong = -1
        tape.append({'ma5': fast[index], 'ma10': medium[index], 'ma20': slow[index],
                     'trend': trend, 'trigger': _trigger(index, fast, medium, gaps, convergence_days),
                     'strong': strong})
    return tape
