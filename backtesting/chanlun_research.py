"""Causal FU structure experiments, deliberately separate from production orders.

This is a documented, conservative operational interpretation, not a claim to
implement every recursive Chan theory definition. Published units never repaint.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, replace
from datetime import date
import math

from backtesting.backtester import FuturesExecutionLedger
from backtesting.independent_research import ResearchRisk, _metrics, causal_prices, planned_lots

ENGINE = 'fu-chanlun-causal-v1'
FAMILIES = {
    'CHAN_SEGMENT_T3': '特征序列线段重叠研究版',
    'CHAN_PEN_T3': '三笔重叠近似对照',
    'RANGE_RETEST': '普通突破回踩',
    'CHANNEL_BREAKOUT': '普通直接突破',
}
SCALES = (.75, 1., 1.25)


@dataclass(frozen=True)
class Unit:
    startIndex: int
    endIndex: int
    startPrice: float
    endPrice: float
    confirmedIndex: int

    @property
    def direction(self):
        return 1 if self.endPrice > self.startPrice else -1

    @property
    def low(self):
        return min(self.startPrice, self.endPrice)

    @property
    def high(self):
        return max(self.startPrice, self.endPrice)


@dataclass(frozen=True)
class Candle:
    high: float
    low: float
    highIndex: int
    lowIndex: int


@dataclass(frozen=True)
class Pivot:
    kind: int
    price: float
    index: int
    mergedIndex: int


def identify_pens(bars, min_span=4):
    """Seal merged candles before recognizing fractals; seal pens one turn later."""
    if min_span < 3:
        raise ValueError('Minimum fractal-center separation is three merged candles')
    sealed, turns, pens, fractals = [], [], [], []
    pending = None
    direction = 1
    for i, bar in enumerate(bars):
        current = Candle(bar.high, bar.low, i, i)
        if pending is None:
            pending = current
            continue
        included = ((current.high <= pending.high and current.low >= pending.low) or
                    (current.high >= pending.high and current.low <= pending.low))
        if included:
            take_high = current.high >= pending.high if direction > 0 else current.high <= pending.high
            take_low = current.low >= pending.low if direction > 0 else current.low <= pending.low
            pending = Candle(current.high if take_high else pending.high,
                             current.low if take_low else pending.low,
                             i if take_high else pending.highIndex,
                             i if take_low else pending.lowIndex)
            continue
        direction = 1 if current.high > pending.high else -1
        sealed.append(pending)
        pending = current
        if len(sealed) < 3:
            continue
        left, middle, right = sealed[-3:]
        top = middle.high > max(left.high, right.high) and middle.low > max(left.low, right.low)
        bottom = middle.high < min(left.high, right.high) and middle.low < min(left.low, right.low)
        if not top and not bottom:
            continue
        p = Pivot(1 if top else -1, middle.high if top else middle.low,
                  middle.highIndex if top else middle.lowIndex, len(sealed) - 2)
        fractals.append({**asdict(p), 'confirmedIndex': i})
        if not turns:
            turns.append(p)
        elif p.kind == turns[-1].kind:
            if p.kind * (p.price - turns[-1].price) > 0:
                turns[-1] = p
        elif (p.mergedIndex - turns[-1].mergedIndex >= min_span and
              p.kind * (p.price - turns[-1].price) > 0):
            turns.append(p)
            if len(turns) >= 3:
                a, b = turns[-3:-1]
                pens.append(Unit(a.index, b.index, a.price, b.price, i))
    return pens, fractals


def _features(pens, start, direction):
    """Fixed segment-direction inclusion policy, explicitly part of this version."""
    features = []
    for index in range(start + 1, len(pens), 2):
        p = pens[index]
        current = {'low': p.low, 'high': p.high, 'turn': index}
        if features:
            old = features[-1]
            included = ((current['low'] >= old['low'] and current['high'] <= old['high']) or
                        (current['low'] <= old['low'] and current['high'] >= old['high']))
            if included:
                choose_new = (current['high'] > old['high'] if direction > 0 else
                              current['low'] < old['low'])
                features[-1] = {
                    'low': max(old['low'], current['low']) if direction > 0 else min(old['low'], current['low']),
                    'high': max(old['high'], current['high']) if direction > 0 else min(old['high'], current['high']),
                    'turn': index if choose_new else old['turn'],
                }
                continue
        features.append(current)
    return features


def _feature_fractals(features, direction):
    for left, middle, right in zip(features, features[1:], features[2:]):
        valid = (middle['high'] > max(left['high'], right['high']) and
                 middle['low'] > max(left['low'], right['low'])) if direction > 0 else (
                 middle['low'] < min(left['low'], right['low']) and
                 middle['high'] < min(left['high'], right['high']))
        if valid:
            yield left, middle, right


class SegmentBuilder:
    def __init__(self):
        self.pens = []
        self.start = 0
        self.initialized = False

    def push(self, pen):
        self.pens.append(pen)
        output = []
        while len(self.pens) - self.start >= 3:
            first = self.pens[self.start:self.start + 3]
            if max(p.low for p in first) >= min(p.high for p in first):
                if not self.initialized:
                    # The data can begin in the middle of an unfinished segment.
                    # Discard only the unclassified leading prefix, never a
                    # previously emitted segment or its agreed successor origin.
                    self.start += 1
                    continue
                break
            self.initialized = True
            direction = first[0].direction
            chosen = None
            for left, middle, right in _feature_fractals(_features(self.pens, self.start, direction), direction):
                turn = middle['turn']
                if turn - self.start < 3:
                    continue
                gap = middle['low'] > left['high'] if direction > 0 else middle['high'] < left['low']
                if gap:
                    price = self.pens[turn].startPrice
                    # A higher/lower extreme while waiting invalidates this old candidate.
                    if any(direction * (p.endPrice - price) > 0 for p in self.pens[turn:]):
                        continue
                    reverse = _features(self.pens, turn, -direction)
                    if not next(_feature_fractals(reverse, -direction), None):
                        continue
                chosen = turn
                break
            if chosen is None:
                break
            a, b = self.pens[self.start], self.pens[chosen]
            output.append(Unit(a.startIndex, b.startIndex, a.startPrice, b.startPrice, pen.confirmedIndex))
            self.start = chosen
        return output


class ZoneMachine:
    def __init__(self, bars, source):
        self.bars, self.source = bars, source
        self.units, self.zones, self.rejections = [], [], []
        self.zone = self.departure = None

    def push(self, unit):
        self.units.append(unit)
        result = []
        if self.zone is not None:
            z = self.zone
            if self.departure is not None:
                direction = self.departure
                boundary = z['upper'] if direction > 0 else z['lower']
                outside = unit.low > boundary if direction > 0 else unit.high < boundary
                observed = self.bars[unit.endIndex:unit.confirmedIndex + 1]
                still_valid = bool(observed) and (min(b.low for b in observed) > boundary if direction > 0 else
                                                 max(b.high for b in observed) < boundary)
                if unit.direction == -direction and outside and still_valid:
                    result.append({'direction': direction, 'pivotIndex': unit.endIndex,
                                   'confirmedIndex': unit.confirmedIndex, 'zoneId': z['id'],
                                   'zoneLower': z['lower'], 'zoneUpper': z['upper'],
                                   'invalidation': boundary, 'source': self.source})
                else:
                    self.rejections.append({'confirmedIndex': unit.confirmedIndex, 'zoneId': z['id'],
                                            'reason': 'PULLBACK_TOUCH_OR_INVALID_BEFORE_CONFIRMATION'})
                self.zone = self.departure = None
            elif unit.direction > 0 and unit.startPrice <= z['upper'] < unit.endPrice:
                self.departure = 1
            elif unit.direction < 0 and unit.startPrice >= z['lower'] > unit.endPrice:
                self.departure = -1
            elif unit.low > z['upper'] or unit.high < z['lower']:
                self.zone = None
        if self.zone is None and len(self.units) >= 3:
            chunk = self.units[-3:]
            low, high = max(u.low for u in chunk), min(u.high for u in chunk)
            if low < high:
                self.zone = {'id': len(self.zones) + 1, 'lower': low, 'upper': high,
                             'startIndex': chunk[0].startIndex, 'confirmedIndex': unit.confirmedIndex,
                             'lastUnitEndIndex': unit.endIndex, 'source': self.source}
                self.zones.append(dict(self.zone))
        return result


def detect(bars, family, scale=1.):
    if family not in FAMILIES or scale not in SCALES:
        raise ValueError('Unknown frozen structure configuration')
    if family.startswith('CHAN_'):
        pens, fractals = identify_pens(bars, int(4 * scale))
        builder = SegmentBuilder()
        segments = []
        for p in pens:
            segments.extend(builder.push(p))
        selected = segments if family == 'CHAN_SEGMENT_T3' else pens
        machine = ZoneMachine(bars, family)
        events = [e for u in selected for e in machine.push(u)]
        return {'events': events, 'pens': [asdict(p) for p in pens],
                'segments': [asdict(p) for p in segments], 'fractals': fractals,
                'zones': machine.zones, 'rejections': machine.rejections}
    period = int(20 * scale)
    pending, events, rejected = None, [], []
    tr = [max(b.high - b.low, abs(b.high - bars[i - 1].close), abs(b.low - bars[i - 1].close))
          if i else b.high - b.low for i, b in enumerate(bars)]
    for i in range(period, len(bars)):
        b = bars[i]
        if pending:
            direction, level, created = pending
            invalid = b.low <= level if direction > 0 else b.high >= level
            if invalid or i - created > 10:
                rejected.append({'confirmedIndex': i, 'reason': 'RETEST_TOUCH_OR_EXPIRED'})
                pending = None
            else:
                atr = sum(tr[max(0, i - 14):i]) / min(14, i)
                near = b.low <= level + .5 * atr if direction > 0 else b.high >= level - .5 * atr
                reversal = direction * (b.close - b.open) > 0 and direction * (b.close - bars[i - 1].close) > 0
                if near and reversal:
                    events.append({'direction': direction, 'pivotIndex': i, 'confirmedIndex': i,
                                   'zoneId': created, 'zoneLower': level, 'zoneUpper': level,
                                   'invalidation': level, 'source': family})
                    pending = None
        if pending is None:
            high, low = max(x.high for x in bars[i - period:i]), min(x.low for x in bars[i - period:i])
            direction = 1 if b.close > high else -1 if b.close < low else 0
            if direction:
                level = high if direction > 0 else low
                if family == 'CHANNEL_BREAKOUT':
                    events.append({'direction': direction, 'pivotIndex': i, 'confirmedIndex': i,
                                   'zoneId': i, 'zoneLower': low, 'zoneUpper': high,
                                   'invalidation': level, 'source': family})
                else:
                    pending = (direction, level, i)
    return {'events': events, 'pens': [], 'segments': [], 'fractals': [], 'zones': [], 'rejections': rejected}


def execute(dataset, events, initial_cash, start: date, end: date, *, cost_multiplier=1,
            risk=None, delay=0, signal_bars=None):
    """Next-open event execution. Only previous observations and the open size orders.

    Reuses the existing cash ledger, sizing and metrics; previous frozen research
    engines remain untouched. Daily stop/target matching is explicitly conditional.
    """
    if initial_cash <= 0 or start > end or cost_multiplier < 1 or not math.isfinite(cost_multiplier) or delay not in (0, 1):
        raise ValueError('Invalid experiment settings')
    risk = risk or ResearchRisk()
    bars = dataset.bars
    signals = causal_prices(dataset) if signal_bars is None else signal_bars
    if len(signals) != len(bars) or any(a.timestamp != b.timestamp for a, b in zip(signals, bars)):
        raise ValueError('Misaligned signal and execution clocks')
    schedule = {}
    for e in events:
        c, p = e['confirmedIndex'], e['pivotIndex']
        if not 0 <= p <= c < len(bars) or e['direction'] not in (-1, 1) or not math.isfinite(e['invalidation']):
            raise ValueError('Invalid causal event')
        index = c + 1 + delay
        if index in schedule:
            raise ValueError('Ambiguous simultaneous events')
        schedule[index] = e
    specs = {k: replace(v, commission_per_lot=v.commission_per_lot * cost_multiplier)
             for k, v in dataset.contract_specs.items()}
    rolls = {e.execution_date: e for e in dataset.roll_events}
    tr = [max(b.high - b.low, abs(b.high - bars[i - 1].close), abs(b.low - bars[i - 1].close))
          if i and b.contract_symbol == bars[i - 1].contract_symbol else b.high - b.low
          for i, b in enumerate(bars)]
    atr = [sum(tr[max(0, i - 13):i + 1]) / min(14, i + 1) for i in range(len(bars))]
    indices = [i for i, b in enumerate(bars) if i >= 80 and start <= b.timestamp.date() <= end]
    ledger = FuturesExecutionLedger(initial_cash)
    entry = None
    fees = slippage = 0.
    curve, trades, decisions, denials = [], [], [], Counter()

    def close(price, bar, reason, slip=None):
        nonlocal entry, fees, slippage
        fill = ledger.close_position(market_price=price, spec=specs[ledger.contract],
                                     slippage_ticks=risk.slippage_ticks * cost_multiplier if slip is None else slip,
                                     fee_rate=risk.fee_rate * cost_multiplier)
        fees += fill.fee; slippage += fill.slippage_cost
        trades.append({**entry, 'exitDate': bar.timestamp.date().isoformat(), 'exitReason': reason,
                       'exitPrice': fill.price, 'closingFee': fill.fee, 'netPnl': fill.trade_net_pnl,
                       'rMultiple': fill.trade_net_pnl / entry['plannedRisk'], 'contract': fill.contract})
        entry = None

    for i in indices:
        b, previous = bars[i], bars[i - 1]
        e = schedule.get(i)
        roll = rolls.get(b.timestamp.date())
        exited = False
        if ledger.direction:
            if roll:
                if ledger.contract != roll.from_contract:
                    raise ValueError('Wrong held delivery contract')
                close(roll.old_open, b, 'ROLL_EXIT'); exited = True
            else:
                if ledger.contract != b.contract_symbol:
                    raise ValueError('Missing delivery roll evidence')
                invalid = ledger.direction * (signals[i - 1].close - entry['invalidation']) <= 0
                if invalid or (e and e['direction'] != ledger.direction) or i - entry['entryIndex'] >= 20:
                    reason = 'STRUCTURE_EXIT' if invalid else 'OPPOSITE_EVENT' if e and e['direction'] != ledger.direction else 'TIME_EXIT'
                    close(b.open, b, reason); exited = True
        if e:
            decision = {'signalDate': bars[e['confirmedIndex']].timestamp.date().isoformat(),
                        'confirmedDate': bars[e['confirmedIndex']].timestamp.date().isoformat(),
                        'pivotDate': bars[e['pivotIndex']].timestamp.date().isoformat(),
                        'executionDate': b.timestamp.date().isoformat(), 'signal': 'BUY' if e['direction'] > 0 else 'SELL',
                        'reason': e['source'], 'outcome': 'POSITION_ALREADY_OPEN', **e}
            decisions.append(decision)
            if not ledger.direction:
                reason = None
                if roll:
                    reason = 'ROLL_DAY_NEW_ORDER_CANCELLED'
                elif exited:
                    reason = 'EXIT_DAY_NO_REENTRY'
                elif any(e['direction'] * (s.close - e['invalidation']) <= 0
                         for s in signals[e['confirmedIndex']:i]):
                    reason = 'STRUCTURE_INVALID_WHILE_WAITING'
                elif e['direction'] * (signals[i].open - e['invalidation']) <= 0:
                    reason = 'STRUCTURE_INVALID_AT_OPEN'
                elif previous.volume < risk.minimum_volume:
                    reason = 'LIQUIDITY'
                if reason:
                    denials[reason] += 1; decision['outcome'] = reason
                else:
                    spec = specs[b.contract_symbol]
                    raw_spec = dataset.contract_specs[b.contract_symbol]
                    planned, unit_risk = planned_lots(ledger.cash, initial_cash, previous.close, atr[i - 1], 2,
                                                     raw_spec, risk, cost_multiplier)
                    actual, actual_risk = planned_lots(ledger.cash, initial_cash, b.open, atr[i - 1], 2,
                                                      raw_spec, risk, cost_multiplier)
                    lots = min(planned, actual, math.floor(previous.volume * risk.participation))
                    if lots < 1:
                        denials['RISK_OR_MARGIN_BELOW_ONE_LOT'] += 1
                        decision['outcome'] = 'RISK_OR_MARGIN_BELOW_ONE_LOT'
                    else:
                        budget = min(ledger.cash, initial_cash) * risk.fraction
                        fill = ledger.open_position(direction=e['direction'], contract=b.contract_symbol,
                            market_price=b.open, spec=spec, margin_rate=risk.margin_rate,
                            margin_budget_ratio=risk.margin_fraction, target_leverage=risk.max_notional,
                            slippage_ticks=risk.slippage_ticks * cost_multiplier,
                            fee_rate=risk.fee_rate * cost_multiplier, fixed_lots=lots)
                        if fill.lots != lots:
                            raise AssertionError('Order sizing and cash ledger disagree')
                        fees += fill.fee; slippage += fill.slippage_cost
                        entry = {**{k: v for k, v in decision.items() if k not in ('outcome', 'executionDate', 'signal', 'reason')},
                                 'entryDate': b.timestamp.date().isoformat(), 'entryIndex': i, 'entryPrice': fill.price,
                                 'direction': ledger.direction, 'lots': lots, 'atr': atr[i - 1],
                                 'riskBudget': budget, 'plannedRisk': max(unit_risk, actual_risk) * lots, 'openingFee': fill.fee}
                        if entry['plannedRisk'] > budget + 1e-7:
                            raise AssertionError('Risk budget exceeded at entry')
                        decision['outcome'] = 'FILLED'
        if ledger.direction:
            tick = specs[ledger.contract].price_tick
            raw_stop = ledger.entry_price - ledger.direction * 2 * entry['atr']
            raw_target = ledger.entry_price + ledger.direction * 4 * entry['atr']
            stop = (math.ceil(raw_stop / tick - 1e-12) if ledger.direction > 0 else math.floor(raw_stop / tick + 1e-12)) * tick
            target = (math.ceil(raw_target / tick - 1e-12) if ledger.direction > 0 else math.floor(raw_target / tick + 1e-12)) * tick
            stopped = b.low <= stop if ledger.direction > 0 else b.high >= stop
            profited = b.high >= target if ledger.direction > 0 else b.low <= target
            if stopped:
                close(min(b.open, stop) if ledger.direction > 0 else max(b.open, stop), b, 'STOP')
            elif profited:
                close(max(b.open, target) if ledger.direction > 0 else min(b.open, target), b, 'TARGET', slip=0)
        if ledger.direction and ledger.equity(b.close, specs[ledger.contract]) <= ledger.margin_occupied(b.close, specs[ledger.contract], risk.margin_rate):
            close(b.close, b, 'MARGIN_LIQUIDATION')
        if i == indices[-1] and ledger.direction:
            close(b.close, b, 'WINDOW_END_LIQUIDATION')
        equity = ledger.equity(b.close, specs[b.contract_symbol])
        curve.append({'date': b.timestamp.date().isoformat(), 'equity': equity,
                      'direction': ledger.direction, 'lots': ledger.lots})
        if equity <= 0:
            denials['BANKRUPTCY_STOP'] += 1
            break
    metrics = _metrics(curve, trades, initial_cash, fees, slippage, denials)
    if abs(metrics['netPnl'] - sum(t['netPnl'] for t in trades)) > 1e-5:
        raise AssertionError('Trade PnL does not reconcile with cash')
    return {'engineVersion': ENGINE, 'metrics': metrics, 'curve': curve, 'trades': trades, 'decisions': decisions}
