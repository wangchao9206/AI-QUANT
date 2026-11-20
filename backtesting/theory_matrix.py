"""Causal entry rules for the independent and combined theory experiments."""

from statistics import mean, median

from backtesting.chanlun_research import detect


THEORIES = ('BASE', 'D', 'W', 'C', 'DW', 'DC', 'WC', 'DWC')
MA_PERIODS = (5, 10, 20)
VOLUME_PERIOD = 20


def dow_structure_up(bars, width=2):
    """Single-series HH/HL proxy, published only after the right-hand bars close."""
    closes = [bar.close for bar in bars]
    highs, lows, states = [], [], []
    for i in range(len(closes)):
        if i >= width * 2:
            pivot = i - width
            neighbors = closes[pivot - width:pivot] + closes[pivot + 1:i + 1]
            price = closes[pivot]
            if price > max(neighbors):
                highs.append(price)
            elif price < min(neighbors):
                lows.append(price)
        states.append(len(highs) >= 2 and len(lows) >= 2
                      and highs[-1] > highs[-2] and lows[-1] > lows[-2])
    return states


def wyckoff_retests(raw_bars, retests):
    """A strong close and expanding breakout volume followed by a quieter retest."""
    result = {}
    for end, event in retests.items():
        breakout = event['zoneId']
        if breakout < VOLUME_PERIOD or breakout >= end:
            continue
        span = raw_bars[breakout - VOLUME_PERIOD:end + 1]
        bar = raw_bars[breakout]
        if not bar.contract_symbol or bar.high <= bar.low:
            continue
        if any(row.contract_symbol != bar.contract_symbol or row.volume <= 0 for row in span):
            continue
        base = median(row.volume for row in raw_bars[breakout - VOLUME_PERIOD:breakout])
        last_location = (bar.close - bar.low) / (bar.high - bar.low)
        retest_ratio = mean(row.volume for row in raw_bars[breakout + 1:end + 1]) / bar.volume
        if bar.volume >= 1.30 * base and last_location >= 0.65 and retest_ratio <= 0.80:
            result[end] = {**event, 'source': 'W', 'breakoutIndex': breakout}
    return result


def events_by_index(bars, family):
    events = [event for event in detect(bars, family)['events'] if event['direction'] == 1]
    result = {event['confirmedIndex']: event for event in events}
    if len(result) != len(events):
        raise ValueError(f'Multiple long candidates confirmed together for {family}')
    return result


def event_at(index, source):
    return {'confirmedIndex': index, 'pivotIndex': index, 'direction': 1,
            'invalidation': 0.0, 'source': source}


def variants(bars, raw_bars, dow_up, *, ma_period=None, wyckoff_setup_bars=10):
    """Use the same standalone setups when combining theories, with Chan as trigger when present.

    D enters on the transition to an uptrend. In a combination it is a state.
    W enters on the completed volume-confirmed retest. For a later C trigger,
    that W setup remains valid until its support breaks, expiry or a roll.
    The optional MA filters the independent entries at their confirmation bars.
    """
    if len(bars) != len(raw_bars) or len(dow_up) != len(bars):
        raise ValueError('Misaligned signal, execution and Dow tapes')
    if ma_period not in (None, *MA_PERIODS) or wyckoff_setup_bars < 1:
        raise ValueError('Unsupported matrix configuration')

    closes = [bar.close for bar in bars]
    retests = events_by_index(bars, 'RANGE_RETEST')
    chan = events_by_index(bars, 'CHAN_PEN_T3')
    wyckoff = wyckoff_retests(raw_bars, retests)
    result = {name: [] for name in THEORIES}
    active_w, was_above = None, False

    for i, bar in enumerate(bars):
        if active_w is not None:
            w_index = active_w['confirmedIndex']
            if (i - w_index > wyckoff_setup_bars or bar.low <= active_w['invalidation']
                    or raw_bars[i].contract_symbol != raw_bars[w_index].contract_symbol):
                active_w = None
        if i in wyckoff:
            active_w = wyckoff[i]

        if ma_period is None:
            above = True
            baseline = retests.get(i)
        else:
            above = i >= ma_period - 1 and bar.close > mean(closes[i + 1 - ma_period:i + 1])
            baseline = event_at(i, f'MA{ma_period}') if i >= ma_period and above and not was_above else None
        was_above = above
        if baseline is not None:
            result['BASE'].append(baseline)
        if not above:
            continue

        if i > 0 and dow_up[i] and not dow_up[i - 1]:
            result['D'].append(event_at(i, 'D'))
        if i in wyckoff:
            result['W'].append(wyckoff[i])
            if dow_up[i]:
                result['DW'].append({**wyckoff[i], 'source': 'DW'})
        if i in chan:
            result['C'].append({**chan[i], 'source': 'C'})
            if dow_up[i]:
                result['DC'].append({**chan[i], 'source': 'DC'})
            if active_w is not None:
                setup = {'wyckoffIndex': active_w['confirmedIndex']}
                result['WC'].append({**chan[i], **setup, 'source': 'WC'})
                if dow_up[i]:
                    result['DWC'].append({**chan[i], **setup, 'source': 'DWC'})
    return result
