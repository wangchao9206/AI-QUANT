"""Causal two-sided Chan and Wyckoff confirmations for the personal MA study."""

from statistics import mean, median

from backtesting.chanlun_research import detect


VOLUME_LOOKBACK = 20
MIN_BREAKOUT_RVOL = 1.30
MIN_DIRECTIONAL_CLOSE = 0.65
MAX_RETEST_VOLUME_RATIO = 0.80


def _wyckoff_confirmations(raw_bars, retests):
    result = []
    for event in retests:
        breakout = event['zoneId']
        confirmed = event['confirmedIndex']
        if not VOLUME_LOOKBACK <= breakout < confirmed:
            continue
        bar = raw_bars[breakout]
        contract = bar.contract_symbol
        if not contract or bar.high <= bar.low:
            continue
        history = raw_bars[breakout - VOLUME_LOOKBACK:breakout]
        retest = raw_bars[breakout + 1:confirmed + 1]
        if any(row.contract_symbol != contract or row.volume <= 0 for row in (*history, bar, *retest)):
            continue
        relative_volume = bar.volume / median(row.volume for row in history)
        close_distance = bar.close - bar.low if event['direction'] == 1 else bar.high - bar.close
        directional_close = close_distance / (bar.high - bar.low)
        retest_volume_ratio = mean(row.volume for row in retest) / bar.volume
        if (relative_volume >= MIN_BREAKOUT_RVOL and directional_close >= MIN_DIRECTIONAL_CLOSE
                and retest_volume_ratio <= MAX_RETEST_VOLUME_RATIO):
            result.append(event)
    return result


def _by_confirmation(events):
    indexed = {event['confirmedIndex']: event for event in events}
    if len(indexed) != len(events):
        raise ValueError('Multiple confirmations in the same signal family and bar')
    return indexed


def _active(event, index, signal, raw_bars, validity_bars):
    confirmed = event['confirmedIndex']
    if (index - confirmed > validity_bars
            or raw_bars[confirmed].contract_symbol != raw_bars[index].contract_symbol):
        return False
    boundary = event['invalidation']
    return signal.low > boundary if event['direction'] == 1 else signal.high < boundary


def overlay_tape(bars, raw_bars, *, validity_bars=10):
    """Publish only completed confirmations, valid through the Nth subsequent bar.

    Signal prices and boundaries share the same causal continuous basis. Only
    volume observations use actual-contract bars. Each new confirmation replaces
    the older confirmation in its family. A boundary touch or roll expires it.
    """
    if (not isinstance(validity_bars, int) or validity_bars < 1
            or len(bars) != len(raw_bars)
            or any(bar.timestamp != raw.timestamp for bar, raw in zip(bars, raw_bars))):
        raise ValueError('Invalid expiry or misaligned signal and actual-contract bars')

    chan = detect(bars, 'CHAN_PEN_T3')['events']
    retests = detect(bars, 'RANGE_RETEST')['events']
    known = {'chan': _by_confirmation(chan),
             'wyckoff': _by_confirmation(_wyckoff_confirmations(raw_bars, retests))}
    active = {}
    output = []
    previous_contract = None
    for index, (bar, raw) in enumerate(zip(bars, raw_bars)):
        if raw.contract_symbol != previous_contract:
            active.clear()
        previous_contract = raw.contract_symbol
        row = {}
        for family, signals in known.items():
            if raw.contract_symbol and index in signals:
                active[family] = signals[index]
            event = active.get(family)
            if event is not None and not _active(event, index, bar, raw_bars, validity_bars):
                active.pop(family)
                event = None
            row[family] = event['direction'] if event else 0
            row[f'{family}ConfirmedIndex'] = event['confirmedIndex'] if event else None
        output.append(row)
    return output
