"""Execute completed daily MA decisions and minute timing on one delivery contract."""

from collections import Counter
from dataclasses import replace
from datetime import datetime, time
from math import isclose, isfinite

from backtesting.backtester import FuturesExecutionLedger
from backtesting.personal_ma_execution import INITIAL_CASH, TRIGGER_SIDES
from data.trading_day import SHANGHAI


def run_multiframe_account(bars, trading_days, daily_signals, spec, start, end, *,
                           confirmations=None, no_add=False, minute_add=False, cost_multiplier=1, wait_days=10):
    """Start flat, buy or sell one lot first, and add at most one long lot."""
    if (len(bars) != len(trading_days) or start > end or wait_days < 0
            or not isfinite(cost_multiplier) or cost_multiplier < 1
            or any(a.timestamp >= b.timestamp for a, b in zip(bars, bars[1:]))
            or any(a > b for a, b in zip(trading_days, trading_days[1:]))
            or any(bar.timestamp.utcoffset() is None or bar.contract_symbol != spec.contract for bar in bars)):
        raise ValueError('Invalid or unordered actual-contract execution inputs')
    daily_dates = sorted(daily_signals)
    day_number = {day: i for i, day in enumerate(daily_dates)}
    all_days = list(dict.fromkeys(trading_days))
    first_day = next((day for day in all_days if start <= day <= end), None)
    if first_day is None or first_day not in day_number or day_number[first_day] == 0:
        raise ValueError('Scoring window requires native bars and a prior completed day')
    active = [(i, bar, day) for i, (bar, day) in enumerate(zip(bars, trading_days)) if start <= day <= end]
    if any(day not in daily_signals for _, _, day in active):
        raise ValueError('A scoring trade day lacks daily signal data')
    previous_day = daily_dates[day_number[first_day] - 1]
    daily_at = lambda day: datetime.combine(day, time(15), SHANGHAI)
    daily = [(daily_at(day), day, daily_signals[day]) for day in daily_dates if previous_day <= day <= end]
    gates = sorted((stamp, (sides,) if isinstance(sides, int) else tuple(sides))
                   for stamp, sides in (confirmations or {}).items() if stamp >= daily[0][0])
    gate_index = daily_index = 0
    ledgers = [FuturesExecutionLedger(INITIAL_CASH / 2) for _ in range(2)]
    entries = [None, None]
    spec = replace(spec, commission_per_lot=spec.commission_per_lot * cost_multiplier)
    fee_rate = .0001 * cost_multiplier
    trades, curve, decisions = [], [], []
    counts, denials = Counter(), Counter()
    latest = pending = None
    close_side = 0
    peak = INITIAL_CASH
    drawdown = fees = slip = 0.0

    def close(slot, stamp, price, reason):
        nonlocal fees, slip
        fill = ledgers[slot].close_position(market_price=price, spec=spec,
                                           slippage_ticks=cost_multiplier, fee_rate=fee_rate)
        fees += fill.fee
        slip += fill.slippage_cost
        trades.append({**entries[slot], 'exitAt': stamp.isoformat(), 'exitPrice': fill.price,
                       'exitReason': reason, 'netPnl': fill.trade_net_pnl})

    def enter(slot, side, stamp, trading_day, price, known, permit, trigger):
        nonlocal fees, slip
        fill = ledgers[slot].open_position(
            direction=side, contract=spec.contract, market_price=price, spec=spec,
            margin_rate=.12, margin_budget_ratio=.20, target_leverage=2,
            slippage_ticks=cost_multiplier, fee_rate=fee_rate, fixed_lots=1,
        )
        if not fill.lots:
            denials['MARGIN'] += 1
            return
        fees += fill.fee
        slip += fill.slippage_cost
        counts['addOpens' if slot else 'primaryOpens'] += 1
        entries[slot] = {'slot': slot, 'direction': side, 'dailyKnownAt': known.isoformat(),
                         'confirmedAt': permit.isoformat(), 'entryAt': stamp.isoformat(),
                         'entryPrice': fill.price, 'entryDay': trading_day.isoformat(),
                         'originTrigger': trigger}
        decisions.append(entries[slot].copy())
        assert known <= permit <= stamp

    for i, bar, trading_day in active:
        stamp = bar.timestamp
        while daily_index < len(daily) and daily[daily_index][0] <= stamp:
            known, day, latest = daily[daily_index]
            trigger = latest['trigger']
            if trigger:
                if pending:
                    denials['REPLACED'] += 1
                close_side = TRIGGER_SIDES[trigger]
                pending = (known, day, trigger, close_side)
                counts['dailyTriggers'] += 1
            daily_index += 1
        available = []
        while gate_index < len(gates) and gates[gate_index][0] <= stamp:
            available.append(gates[gate_index])
            gate_index += 1
        previous_pending = pending
        held = ledgers[0].direction
        if close_side and held == -close_side and bar.volume > 0:
            for slot, ledger in enumerate(ledgers):
                if ledger.direction:
                    close(slot, stamp, bar.open, 'MA_REVERSAL')
            held = close_side = 0
        elif close_side and held != -close_side:
            close_side = 0

        if pending:
            known, day, trigger, side = pending
            add = trigger == 'LONG_REENTRY' and held == 1
            age = day_number[trading_day] - day_number[day]
            failure = None
            if (latest is None or latest['trend'] != side):
                failure = 'MA_DIRECTION_LOST'
            elif age > wait_days:
                failure = 'EXPIRED'
            elif held == side and not add:
                failure = 'ALREADY_IN_DIRECTION'
            elif add and (no_add or ledgers[1].direction):
                failure = 'ADD_DISABLED' if no_add else 'ALREADY_ADDED'
            if failure:
                denials[failure] += 1
                pending = None
            else:
                permit = known if confirmations is None else next(
                    (confirmed for confirmed, sides in available if known <= confirmed and side in sides), None)
                if permit is not None and bar.volume > 0 and held != -side:
                    enter(int(add), side, stamp, trading_day, bar.open, known, permit, trigger)
                    pending = None
        if (minute_add and not no_add and previous_pending is None and latest and latest['trend'] == 1
                and ledgers[0].direction == 1 and not ledgers[1].direction and bar.volume > 0):
            after_open = datetime.fromisoformat(entries[0]['entryAt'])
            permit = next((confirmed for confirmed, sides in available if after_open < confirmed and 1 in sides), None)
            if permit is not None:
                enter(1, 1, stamp, trading_day, bar.open, datetime.fromisoformat(entries[0]['dailyKnownAt']),
                      permit, 'FRESH_MINUTE_ADD')
        counts['exposedBars'] += int(bool(ledgers[0].direction))
        counts['twoLotBars'] += int(bool(ledgers[1].direction))
        if i == active[-1][0]:
            if pending:
                denials['WINDOW_ENDED'] += 1
            if bar.volume <= 0 and ledgers[0].direction:
                raise ValueError('Terminal mark requires a traded bar')
            terminal = datetime.combine(trading_day, time(15), SHANGHAI)
            if terminal < stamp:
                raise ValueError('End-of-window close is earlier than its bar')
            for slot, ledger in enumerate(ledgers):
                if ledger.direction:
                    close(slot, terminal, bar.close, 'WINDOW_END')
        equity = sum(book.equity(bar.close, spec) for book in ledgers)
        peak = max(peak, equity)
        drawdown = max(drawdown, (peak - equity) / peak)
        curve.append({'at': stamp.isoformat(), 'equity': equity, 'lots': sum(book.lots for book in ledgers)})

    pnl = curve[-1]['equity'] - INITIAL_CASH
    if not isclose(sum(t['netPnl'] for t in trades), pnl, rel_tol=1e-10, abs_tol=1e-6):
        raise AssertionError('Minute execution cash failed to reconcile')
    if len(trades) != counts['primaryOpens'] + counts['addOpens']:
        raise AssertionError('Minute execution has unmatched legs')
    metrics = {**counts, 'initialCash': INITIAL_CASH, 'netPnl': pnl,
               'returnPct': pnl / INITIAL_CASH * 100, 'maxDrawdownPct': drawdown * 100,
               'exposurePct': counts['exposedBars'] / len(active) * 100,
               'primaryOpens': counts['primaryOpens'], 'addOpens': counts['addOpens'],
               'closedTrades': len(trades), 'fees': fees, 'slippageCost': slip,
               'longNetPnl': sum(t['netPnl'] for t in trades if t['direction'] > 0),
               'shortNetPnl': sum(t['netPnl'] for t in trades if t['direction'] < 0),
               'addNetPnl': sum(t['netPnl'] for t in trades if t['slot'] == 1), 'denials': dict(denials)}
    return {'metrics': metrics, 'curve': curve, 'trades': trades, 'decisions': decisions}
