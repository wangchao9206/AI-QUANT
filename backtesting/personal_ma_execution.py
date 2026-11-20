"""Daily execution for the personal MA5/MA10/MA20 research variants."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from math import isclose, isfinite, sqrt
from statistics import mean, pstdev

from backtesting.backtester import FuturesExecutionLedger


INITIAL_CASH = 1_000_000
VARIANTS = ('MA', 'MA_NO_ADD', 'MA_C', 'MA_W', 'MA_CW', 'MA_CW_ADD')
TRIGGER_SIDES = {'LONG_CROSS': 1, 'SHORT_CROSS': -1, 'LONG_REENTRY': 1}
OVERLAY_KEYS = {'MA_C': ('chan',), 'MA_W': ('wyckoff',), 'MA_CW': ('chan', 'wyckoff')}


@dataclass(frozen=True)
class Setup:
    index: int
    trigger: str
    side: int


def required_overlays(variant, is_add):
    if variant == 'MA_CW_ADD' and is_add:
        return OVERLAY_KEYS['MA_CW']
    return OVERLAY_KEYS.get(variant, ())


def run_account(dataset, signals, overlay, start, end, variant, *, cost_multiplier=1, wait_bars=10):
    """Execute prior-close triggers using actual delivery opens and two one-lot sleeves."""
    bars = dataset.bars
    if (not dataset.complete or len(bars) != len(signals) or len(bars) != len(overlay)
            or start > end or variant not in VARIANTS or wait_bars < 0
            or not isfinite(cost_multiplier) or cost_multiplier < 1):
        raise ValueError('Invalid personal MA experiment inputs')
    dates = [bar.timestamp.date() for bar in bars]
    if any(a >= b for a, b in zip(dates, dates[1:])):
        raise ValueError('Expected strictly ordered daily delivery bars')
    indices = [i for i in range(1, len(bars)) if start <= dates[i] <= end]
    if not indices:
        raise ValueError('No daily execution bars in the selected window')

    rolls = {event.execution_date: event for event in dataset.roll_events}
    specs = {key: replace(spec, commission_per_lot=spec.commission_per_lot * cost_multiplier)
             for key, spec in dataset.contract_specs.items()}
    ledgers = [FuturesExecutionLedger(INITIAL_CASH / 2) for _ in range(2)]
    entries = [None, None]
    fee_rate = .0001 * cost_multiplier
    trades, curve, decisions = [], [], []
    denials, starts, exits, trigger_counts, exposure = (Counter() for _ in range(5))
    fees = slippage = 0.0
    pending = None
    flatten_to = 0

    def open_leg(slot, i, side, price, setup, confirmation, reason):
        nonlocal fees, slippage
        ledger = ledgers[slot]
        spec = specs[bars[i].contract_symbol]
        fill = ledger.open_position(
            direction=side, contract=spec.contract, market_price=price, spec=spec,
            margin_rate=.12, margin_budget_ratio=.20, target_leverage=2,
            slippage_ticks=cost_multiplier, fee_rate=fee_rate, fixed_lots=1,
        )
        if fill.lots != 1:
            denials['MARGIN_NO_LOT'] += 1
            return False
        fees += fill.fee
        slippage += fill.slippage_cost
        starts[reason] += 1
        if reason != 'ROLL':
            starts['LONG_SIGNAL' if side > 0 else 'SHORT_SIGNAL'] += 1
        entries[slot] = {
            'slot': slot, 'direction': side, 'contract': fill.contract, 'lots': fill.lots,
            'entryIndex': i, 'entryDate': dates[i].isoformat(), 'entryPrice': fill.price,
            'entryReason': reason, 'originTrigger': setup.trigger,
            'signalIndex': setup.index, 'signalDate': dates[setup.index].isoformat(),
            'approvalIndex': confirmation, 'approvalDate': dates[confirmation].isoformat(),
            'openingFee': fill.fee, 'openingSlippage': fill.slippage_cost,
        }
        return True

    def close_leg(slot, i, price, reason):
        nonlocal fees, slippage
        ledger = ledgers[slot]
        entry = entries[slot]
        fill = ledger.close_position(
            market_price=price, spec=specs[ledger.contract],
            slippage_ticks=cost_multiplier, fee_rate=fee_rate,
        )
        fees += fill.fee
        slippage += fill.slippage_cost
        exits[reason] += 1
        trades.append({**entry, 'exitIndex': i, 'exitDate': dates[i].isoformat(),
                       'exitReason': reason, 'exitPrice': fill.price, 'closingFee': fill.fee,
                       'closingSlippage': fill.slippage_cost, 'netPnl': fill.trade_net_pnl})
        entries[slot] = None
        return entry

    def note(i, setup, outcome, **detail):
        decisions.append({'executionDate': dates[i].isoformat(), 'triggerDate': dates[setup.index].isoformat(),
                          'trigger': setup.trigger, 'direction': setup.side, 'outcome': outcome, **detail})

    for i in indices:
        bar, prior = bars[i], i - 1
        roll = rolls.get(dates[i])
        signal = signals[prior]
        trigger = signal['trigger']
        if trigger is not None:
            trigger_counts[trigger] += 1
            next_setup = Setup(prior, trigger, TRIGGER_SIDES[trigger])
            if pending is not None:
                denials['SETUP_REPLACED'] += 1
                note(i, pending, 'SETUP_REPLACED')
            pending = next_setup
            flatten_to = next_setup.side

        if roll is not None:
            for slot, ledger in enumerate(ledgers):
                side = ledger.direction
                if not side:
                    continue
                if ledger.contract != roll.from_contract or bar.contract_symbol != roll.to_contract:
                    raise ValueError('Open sleeve does not match observed roll legs')
                reverse = bool(flatten_to and side != flatten_to)
                entry = close_leg(slot, i, roll.old_open, 'MA_REVERSAL' if reverse else 'ROLL')
                if not reverse:
                    if bar.volume > 0:
                        setup = Setup(entry['signalIndex'], entry['originTrigger'], side)
                        open_leg(slot, i, side, roll.new_open, setup, entry['approvalIndex'], 'ROLL')
                    else:
                        denials['ROLL_NEW_LEG_NO_VOLUME'] += 1
            flatten_to = 0
        elif flatten_to:
            opposite = [slot for slot, ledger in enumerate(ledgers)
                        if ledger.direction == -flatten_to]
            if opposite and bar.volume <= 0:
                denials['EXIT_NO_VOLUME'] += len(opposite)
            else:
                for slot in opposite:
                    close_leg(slot, i, bar.open, 'MA_REVERSAL')
                flatten_to = 0

        if pending is not None:
            side = pending.side
            held = ledgers[0].direction or ledgers[1].direction
            is_add = pending.trigger == 'LONG_REENTRY' and held == 1
            overlays = required_overlays(variant, is_add)
            failure = None
            if prior - pending.index > wait_bars:
                failure = 'SETUP_EXPIRED'
            elif signal['trend'] != side:
                failure = 'SETUP_LOST_MA_TREND'
            elif held == side and not is_add:
                failure = 'ALREADY_IN_DIRECTION'
            elif is_add and (variant == 'MA_NO_ADD' or ledgers[1].direction):
                failure = 'ADD_DISABLED' if variant == 'MA_NO_ADD' else 'ADD_SLOT_OCCUPIED'
            if failure:
                denials[failure] += 1
                note(i, pending, failure)
                pending = None
            elif overlays and not all(overlay[prior][key] == side for key in overlays):
                note(i, pending, 'WAIT_FOR_OVERLAY', overlays={key: overlay[prior][key] for key in overlays})
            elif overlays and roll is not None:
                denials['GATED_OPEN_DEFERRED_ON_ROLL'] += 1
                note(i, pending, 'GATED_OPEN_DEFERRED_ON_ROLL')
            else:
                if bar.volume <= 0 or held == -side:
                    denials['ENTRY_NO_EXECUTABLE_OPEN'] += 1
                    note(i, pending, 'ENTRY_NO_EXECUTABLE_OPEN')
                else:
                    slot = 1 if is_add else 0
                    price = roll.new_open if roll is not None else bar.open
                    reason = 'ADD' if is_add else 'PRIMARY'
                    opened = open_leg(slot, i, side, price, pending, prior, reason)
                    note(i, pending, f'OPEN_{reason}' if opened else 'MARGIN_NO_LOT',
                         approvalDate=dates[prior].isoformat())
                pending = None

        occupied = [ledger for ledger in ledgers if ledger.direction]
        if any(ledger.contract != bar.contract_symbol for ledger in occupied):
            raise ValueError('Held delivery contract changed without an observed roll')
        if len(occupied) > 1 and occupied[0].direction != occupied[1].direction:
            raise AssertionError('Opposing sleeves cannot coexist')
        if occupied:
            direction_key = 'LONG' if occupied[0].direction > 0 else 'SHORT'
            exposure[direction_key] += 1
            exposure['TWO_LOTS'] += len(occupied) == 2
            exposure['STRONG'] += signals[i]['strong'] == occupied[0].direction
        if i == indices[-1]:
            if pending is not None:
                denials['SETUP_WINDOW_ENDED'] += 1
                note(i, pending, 'SETUP_WINDOW_ENDED')
            if occupied and bar.volume <= 0:
                raise ValueError('Terminal liquidation requires observed trading')
            for slot, ledger in enumerate(ledgers):
                if ledger.direction:
                    close_leg(slot, i, bar.close, 'WINDOW_END')

        equity = sum(ledger.equity(bar.close, specs[bar.contract_symbol]) for ledger in ledgers)
        curve.append({'date': dates[i].isoformat(), 'equity': equity,
                      'direction': ledgers[0].direction or ledgers[1].direction,
                      'lots': sum(ledger.lots for ledger in ledgers)})

    metrics = score(curve, trades, fees, slippage, denials, starts, exits, trigger_counts, exposure)
    if (not isclose(metrics['netPnl'], sum(row['netPnl'] for row in trades), rel_tol=1e-10, abs_tol=1e-6)
            or starts.total() - starts['LONG_SIGNAL'] - starts['SHORT_SIGNAL'] != len(trades)
            or any(not row['signalIndex'] <= row['approvalIndex'] < row['entryIndex'] <= row['exitIndex']
                   for row in trades)):
        raise AssertionError('Personal MA ledger chronology or cash does not reconcile')
    return {'metrics': metrics, 'curve': curve, 'trades': trades, 'decisions': decisions}


def score(curve, trades, fees, slippage, denials, starts, exits, trigger_counts, exposure):
    equities = [INITIAL_CASH, *(row['equity'] for row in curve)]
    peak, drawdown = INITIAL_CASH, 0.0
    for value in equities:
        peak = max(peak, value)
        drawdown = max(drawdown, (peak - value) / peak)
    returns = [new / old - 1 for old, new in zip(equities, equities[1:]) if old > 0]
    deviation = pstdev(returns) if len(returns) > 1 else 0
    long_trades = [row for row in trades if row['direction'] > 0]
    short_trades = [row for row in trades if row['direction'] < 0]
    wins = sum(row['netPnl'] > 0 for row in trades)
    held_days = exposure['LONG'] + exposure['SHORT']
    return {
        'initialCash': INITIAL_CASH, 'finalEquity': equities[-1], 'netPnl': equities[-1] - INITIAL_CASH,
        'returnPct': (equities[-1] / INITIAL_CASH - 1) * 100, 'maxDrawdownPct': drawdown * 100,
        'sharpe': mean(returns) / deviation * sqrt(250) if deviation else 0.0,
        'closedTrades': len(trades), 'winningTrades': wins, 'winRatePct': wins / len(trades) * 100 if trades else None,
        'strategyClosures': exits['MA_REVERSAL'], 'rollCloses': exits['ROLL'], 'rollOpens': starts['ROLL'],
        'terminalCloses': exits['WINDOW_END'], 'longCloses': len(long_trades), 'shortCloses': len(short_trades),
        'primaryOpens': starts['PRIMARY'], 'addOpens': starts['ADD'], 'longOpenSignals': starts['LONG_SIGNAL'],
        'shortOpenSignals': starts['SHORT_SIGNAL'], 'longNetPnl': sum(row['netPnl'] for row in long_trades),
        'shortNetPnl': sum(row['netPnl'] for row in short_trades),
        'addNetPnl': sum(row['netPnl'] for row in trades if row['slot'] == 1),
        'fees': fees, 'slippageCost': slippage, 'days': len(curve), 'daysInPosition': held_days,
        'daysInPositionPct': held_days / len(curve) * 100,
        'longDays': exposure['LONG'], 'shortDays': exposure['SHORT'], 'twoLotDays': exposure['TWO_LOTS'],
        'strongPositionDays': exposure['STRONG'], 'triggers': dict(trigger_counts), 'denials': dict(denials),
    }
