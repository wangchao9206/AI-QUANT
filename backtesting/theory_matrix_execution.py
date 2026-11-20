"""Execute completed intraday signal bars on native one-minute contract prices."""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import Counter
from dataclasses import replace
from datetime import time, timedelta
from math import ceil, isclose, isfinite
from statistics import mean
from zoneinfo import ZoneInfo

from backtesting.backtester import FuturesExecutionLedger


INITIAL_CASH = 1_000_000
MAX_HOLD_MINUTES = 240
LIQUIDATION_TIME = time(14, 59)
SHANGHAI = ZoneInfo('Asia/Shanghai')
ONE_MINUTE = timedelta(minutes=1)


def _atr(bars):
    true_ranges = []
    for i, bar in enumerate(bars):
        previous_close = bars[i - 1].close if i else bar.open
        true_ranges.append(max(bar.high - bar.low, abs(bar.high - previous_close),
                               abs(bar.low - previous_close)))
    return [None if i < 13 else mean(true_ranges[i - 13:i + 1])
            for i in range(len(bars))]


def _schedule(bars, dates, signal_bars, events, first, last, cutoff, denials):
    """Map bar-end availability onto the first subsequent native open."""
    starts = [bar.timestamp for bar in bars]
    date_by_start = dict(zip(starts, dates))
    atr = _atr(signal_bars)
    orders = {}
    for event in events:
        i = event['confirmedIndex']
        if not 0 <= i < len(signal_bars) or event['direction'] != 1:
            raise ValueError('Expected a long event at a valid signal-bar index')
        known_at = signal_bars[i].timestamp
        signal_day = date_by_start.get(known_at - ONE_MINUTE)
        if signal_day is None:
            raise ValueError('Signal bar does not end on a verified native minute')
        if not dates[first] <= signal_day <= dates[last - 1]:
            continue
        j = bisect_left(starts, known_at, lo=first, hi=last)
        if j >= last or dates[j] != signal_day or cutoff[j]:
            denials['NO_OPEN_BEFORE_DAILY_LIQUIDATION'] += 1
            continue
        if atr[i] is None or atr[i] <= 0:
            denials['ATR_UNAVAILABLE'] += 1
            continue
        invalidation = event.get('invalidation')
        if invalidation is not None and not isfinite(invalidation):
            raise ValueError('Invalid structure boundary')
        if j in orders:
            raise ValueError('Ambiguous simultaneous intraday entry events')
        orders[j] = (known_at, atr[i], invalidation)
    return orders


def run_minute_execution(bars, trading_days, signal_bars, seconds, events, start, end,
                         spec, cost_multiplier):
    """Simulate long-only fixed-lot accounts with a shared native-minute holding cap.

    A zero-volume minute cannot fill. Day liquidation is a required known open,
    and a gap stop takes priority over time or structure exits. A target is a
    limit scenario. Trade chronology uses raw open timestamps and bar-end signals.
    """
    if (seconds not in (900, 1800, 3600) or start > end or cost_multiplier < 1
            or not isfinite(cost_multiplier) or len(bars) != len(trading_days)):
        raise ValueError('Invalid intraday execution settings')
    if (not all(isfinite(value) for value in (spec.price_tick, spec.margin_per_lot,
                                             spec.volume_multiple, spec.commission_per_lot))
            or min(spec.price_tick, spec.margin_per_lot, spec.volume_multiple) <= 0
            or spec.commission_per_lot < 0):
        raise ValueError('Invalid delivery-contract specifications')
    if (any(bar.timestamp.utcoffset() is None for tape in (bars, signal_bars) for bar in tape)
            or any(a.timestamp >= b.timestamp for a, b in zip(bars, bars[1:]))
            or any(a.timestamp >= b.timestamp for a, b in zip(signal_bars, signal_bars[1:]))
            or any(a > b for a, b in zip(trading_days, trading_days[1:]))
            or any(bar.contract_symbol != spec.contract for bar in bars)):
        raise ValueError('Unordered or mismatched native contract tape')

    first = bisect_left(trading_days, start)
    last = bisect_right(trading_days, end, lo=first)
    if first == last:
        raise ValueError('No native trading minutes in the requested window')
    cutoff = {i: bars[i].timestamp.astimezone(SHANGHAI).time() == LIQUIDATION_TIME
              for i in range(first, last)}
    for i in range(first, last):
        last_of_day = i == last - 1 or trading_days[i] != trading_days[i + 1]
        if cutoff[i] != last_of_day or (last_of_day and bars[i].volume <= 0):
            raise ValueError(f'Missing executable 14:59 liquidation on {trading_days[i]}')

    denials = Counter()
    orders = _schedule(bars, trading_days, signal_bars, events, first, last, cutoff, denials)
    scheduled = len(orders) + sum(denials.values())
    ledger = FuturesExecutionLedger(INITIAL_CASH)
    spec = replace(spec, commission_per_lot=spec.commission_per_lot * cost_multiplier)
    slippage_ticks = cost_multiplier
    fee_rate = .0001 * cost_multiplier
    fees = slippage = 0.0
    pnl, net_r, durations = [], [], []
    exit_counts = Counter()
    entry = None
    peak = INITIAL_CASH
    drawdown = 0.0
    exposed = 0
    total_lots = 0

    def close(index, price, reason, limit=False, intrabar=False):
        nonlocal fees, slippage, entry
        fill = ledger.close_position(market_price=price, spec=spec, fee_rate=fee_rate,
                                     slippage_ticks=0 if limit else slippage_ticks)
        fees += fill.fee
        slippage += fill.slippage_cost
        pnl.append(fill.trade_net_pnl)
        net_r.append(fill.trade_net_pnl / entry['initialRisk'])
        durations.append(index - entry['index'] + int(intrabar))
        exit_counts[reason] += 1
        entry = None

    for i in range(first, last):
        bar = bars[i]
        traded = bar.volume > 0
        exited = False
        if entry is not None and traded:
            if bar.open <= entry['stop']:
                close(i, bar.open, 'STOP_GAP')
            elif cutoff[i]:
                close(i, bar.open, 'DAY_END')
            elif i - entry['index'] >= MAX_HOLD_MINUTES:
                close(i, bar.open, 'TIME')
            elif entry['invalidated']:
                close(i, bar.open, 'STRUCTURE_EXIT')
            elif bar.open >= entry['target']:
                close(i, entry['target'], 'TARGET_GAP_CAPPED', limit=True)
            exited = entry is None

        if i in orders:
            known_at, atr, invalidation = orders[i]
            assert known_at <= bar.timestamp
            if not traded:
                denials['ZERO_VOLUME_OPEN'] += 1
            elif entry is not None or exited:
                denials['POSITION_ALREADY_OPEN' if entry is not None else 'EXIT_MINUTE_NO_REENTRY'] += 1
            elif invalidation is not None and bar.open <= invalidation:
                denials['STRUCTURE_INVALID_AT_OPEN'] += 1
            else:
                entry_price = ledger._fill_price(bar.open, 1, spec, slippage_ticks)
                tick = spec.price_tick
                stop = ceil((entry_price - 2 * atr) / tick - 1e-12) * tick
                target = ceil((entry_price + 4 * atr) / tick - 1e-12) * tick
                if stop <= 0 or stop >= entry_price - 1e-12:
                    denials['INVALID_STOP_DISTANCE'] += 1
                else:
                    fill = ledger.open_position(direction=1, contract=spec.contract,
                                                market_price=bar.open, spec=spec, margin_rate=.12,
                                                margin_budget_ratio=.20, target_leverage=2,
                                                slippage_ticks=slippage_ticks, fee_rate=fee_rate,
                                                fixed_lots=1)
                    if fill.lots != 1:
                        denials['MARGIN'] += 1
                    else:
                        fees += fill.fee
                        slippage += fill.slippage_cost
                        total_lots += fill.lots
                        stop_fill = ledger._fill_price(stop, -1, spec, slippage_ticks)
                        unit_risk = ((fill.price - stop_fill) * spec.volume_multiple + fill.fee
                                     + ledger._fee(stop_fill, 1, spec, fee_rate))
                        entry = {'index': i, 'stop': stop, 'target': target, 'invalidation': invalidation,
                                 'invalidated': False, 'initialRisk': unit_risk}

        if entry is not None:
            exposed += 1
            if traded:
                if bar.low <= entry['stop']:
                    close(i, entry['stop'], 'STOP', intrabar=True)
                elif bar.high >= entry['target']:
                    close(i, entry['target'], 'TARGET', limit=True, intrabar=True)
                elif entry['invalidation'] is not None:
                    entry['invalidated'] = bar.close <= entry['invalidation']

        equity = ledger.equity(bar.close, spec)
        peak = max(peak, equity)
        drawdown = max(drawdown, (peak - equity) / peak)

    net = ledger.cash - INITIAL_CASH
    trade_count = len(pnl)
    if (entry is not None or trade_count != total_lots or sum(durations) != exposed
            or scheduled != trade_count + sum(denials.values())
            or not isclose(sum(pnl), net, rel_tol=1e-10, abs_tol=1e-7)):
        raise AssertionError('Intraday execution does not reconcile')
    winners = sum(value > 0 for value in pnl)
    gross_gain = sum(max(0, value) for value in pnl)
    gross_loss = sum(max(0, -value) for value in pnl)
    exposure = exposed / (last - first) * 100
    return {'initialCash': INITIAL_CASH, 'finalEquity': ledger.cash, 'netPnl': net,
            'returnPct': net / INITIAL_CASH * 100, 'maxDrawdownPct': drawdown * 100,
            'closedTrades': trade_count, 'winningTrades': winners,
            'winRatePct': winners / trade_count * 100 if trade_count else None,
            'profitFactor': gross_gain / gross_loss if gross_loss > 0 else None,
            'meanR': mean(net_r) if net_r else None, 'totalR': sum(net_r),
            'scheduled': scheduled, 'denials': dict(denials), 'exits': dict(exit_counts),
            'fees': fees, 'slippageCost': slippage, 'daysInPositionPct': exposure,
            'exposurePct': exposure, 'holdingMinutes': exposed, 'observedMinutes': last - first,
            'meanHoldMinutes': mean(durations) if durations else None}
