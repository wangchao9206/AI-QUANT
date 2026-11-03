"""AI-QUANT's independently implemented, causal Chan research kernel.

No third-party calculation imports. This is a named operational profile, not a
claim to reproduce another engine's private rules or every reading of the text.
Merged candles are sealed before fractals; a stroke is sealed only when the
next valid opposite stroke exists. Dynamic tails remain explicitly provisional.
"""
from dataclasses import dataclass
import math

VERSION = 'aiquant-chan-v1'
PARAMETERS = {
    'initialInclusionDirection': 'UP',
    'fractalConfirmation': 'RIGHT_MERGED_CANDLE_SEALED',
    'minimumFractalCenterDistance': 4,
    'strokeConfirmation': 'FOLLOWING_OPPOSITE_STROKE',
    'featureInclusionDirection': 'SEGMENT_DIRECTION',
    'segmentGapConfirmation': 'REVERSE_FEATURE_FRACTAL',
    'zoneBasis': 'CONFIRMED_BI',
    'zoneBoundary': 'FIXED_INITIAL_THREE_STROKE_INTERSECTION',
    'macd': [12, 26, 9],
    'divergenceAreaRatio': 0.9,
    'firstPointContext': 'TWO_NON_OVERLAPPING_TREND_ZONES',
    'signalQualification': 'RESEARCH_CANDIDATE_ONLY',
}


@dataclass(frozen=True)
class Merged:
    high: float
    low: float
    high_index: int
    low_index: int
    indices: tuple


@dataclass(frozen=True)
class Fractal:
    kind: int  # top +1; bottom -1
    price: float
    index: int
    position: int
    observed: int
    evidence: tuple


@dataclass(frozen=True)
class Stroke:
    start: int
    end: int
    a: float
    b: float
    observed: int

    @property
    def direction(self): return 1 if self.b > self.a else -1
    @property
    def low(self): return min(self.a, self.b)
    @property
    def high(self): return max(self.a, self.b)


def primitive(kind, item, sure=True, **extra):
    return {'type': kind, 'startIndex': item.start, 'endIndex': item.end,
            'startPrice': item.a, 'endPrice': item.b,
            'direction': 'UP' if item.direction > 0 else 'DOWN',
            'engineConfirmed': sure, 'rawFlag': 'AIQUANT_SEALED' if sure else 'AIQUANT_DYNAMIC', **extra}


def fractal_record(f):
    return {'type': 'FRACTAL', 'startIndex': f.index, 'endIndex': f.index,
            'startPrice': f.price, 'endPrice': f.price,
            'direction': 'DOWN' if f.kind > 0 else 'UP', 'engineConfirmed': True,
            'rawFlag': 'AIQUANT_SEALED_THREE_CANDLE_FRACTAL',
            'evidence': {'ruleId': 'SEALED_THREE_MERGED_CANDLES_V1',
                         'fractalKind': 'TOP' if f.kind > 0 else 'BOTTOM',
                         'sourceBarIndices': list(f.evidence), 'confirmedIndex': f.observed,
                         'referenceLessons': [62]}}


def feature_sequence(pens, start, direction):
    """Opposite strokes, with explicit directional inclusion and provenance."""
    result = []
    for number in range(start + 1, len(pens), 2):
        pen = pens[number]
        item = {'low': pen.low, 'high': pen.high, 'turn': number, 'members': [number]}
        if result:
            previous = result[-1]
            included = ((item['low'] >= previous['low'] and item['high'] <= previous['high'])
                        or (item['low'] <= previous['low'] and item['high'] >= previous['high']))
            if included:
                choose = item['high'] > previous['high'] if direction > 0 else item['low'] < previous['low']
                combine = max if direction > 0 else min
                result[-1] = {'low': combine(previous['low'], item['low']),
                              'high': combine(previous['high'], item['high']),
                              'turn': number if choose else previous['turn'],
                              'members': previous['members'] + [number]}
                continue
        result.append(item)
    return result


def feature_turns(features, direction):
    for left, middle, right in zip(features, features[1:], features[2:]):
        top = middle['high'] > max(left['high'], right['high']) and middle['low'] > max(left['low'], right['low'])
        bottom = middle['low'] < min(left['low'], right['low']) and middle['high'] < min(left['high'], right['high'])
        if top if direction > 0 else bottom:
            yield left, middle, right


class SegmentModel:
    def __init__(self):
        self.pens = []
        self.start = 0
        self.initialized = False
        self.segments = []
        self.evidence = []

    def push(self, pen):
        self.pens.append(pen)
        while len(self.pens) - self.start >= 3:
            first = self.pens[self.start:self.start + 3]
            if max(p.low for p in first) >= min(p.high for p in first):
                if not self.initialized:
                    self.start += 1
                    continue
                return
            self.initialized = True
            direction = first[0].direction
            found = None
            for left, middle, right in feature_turns(feature_sequence(self.pens, self.start, direction), direction):
                turn = middle['turn']
                if turn - self.start < 3:
                    continue
                gap = middle['low'] > left['high'] if direction > 0 else middle['high'] < left['low']
                if gap:
                    extreme = self.pens[turn].a
                    if any(direction * (p.b - extreme) > 0 for p in self.pens[turn:]):
                        continue
                    reverse = list(feature_turns(feature_sequence(self.pens, turn, -direction), -direction))
                    if not reverse:
                        continue
                found = (turn, gap, [left, middle, right])
                break
            if found is None:
                return
            turn, gap, features = found
            origin, endpoint = self.pens[self.start], self.pens[turn]
            self.segments.append(Stroke(origin.start, endpoint.start, origin.a, endpoint.a, pen.observed))
            self.evidence.append({'ruleId': 'SEGMENT_FEATURE_FRACTAL_V1', 'hasFeatureGap': gap,
                                  'featureSequence': features, 'sourceStrokePositions': list(range(self.start, turn)),
                                  'confirmedIndex': pen.observed, 'referenceLessons': [67]})
            self.start = turn


class ZoneSignalModel:
    """Fixed-core pen zones and explicitly provisional B1/B2/B3 candidates."""
    def __init__(self, bars, histogram):
        self.bars, self.histogram = bars, histogram
        self.pens, self.zones, self.signals = [], [], []
        self.active = self.departure = None
        self.first_points = {}

    def area(self, pen):
        return sum(max(0., pen.direction * value) for value in self.histogram[pen.start:pen.end + 1])

    def clear_since_pivot(self, direction, pivot, level, observed):
        tail = self.bars[pivot + 1:observed + 1]
        return all(b['low'] > level if direction > 0 else b['high'] < level for b in tail)

    def candidate(self, category, pen, direction, invalidation, evidence):
        if not self.clear_since_pivot(direction, pen.end, invalidation, pen.observed):
            return None
        signal = {'type': 'BSP', 'startIndex': pen.end, 'endIndex': pen.end,
                  'startPrice': pen.b, 'endPrice': pen.b, 'direction': 'UP' if direction > 0 else 'DOWN',
                  'engineConfirmed': True, 'rawFlag': 'AIQUANT_RESEARCH_CANDIDATE',
                  'identityScope': category, 'signalType': category, 'signalState': 'CANDIDATE',
                  'invalidation': invalidation, 'candidateObservedIndex': pen.observed,
                  'evidence': evidence}
        self.signals.append(signal)
        return signal

    def invalidate(self, bar):
        for signal in self.signals:
            if signal['signalState'] != 'CANDIDATE' or bar['index'] <= signal['candidateObservedIndex']:
                continue
            broken = bar['low'] <= signal['invalidation'] if signal['direction'] == 'UP' else bar['high'] >= signal['invalidation']
            if broken:
                signal.update(signalState='INVALIDATED', invalidatedIndex=bar['index'], engineConfirmed=False)

    def push(self, pen):
        self.pens.append(pen)
        number = len(self.pens) - 1
        if self.active is not None:
            zone = self.active
            if self.departure is not None:
                direction, origin = self.departure
                boundary = zone['high'] if direction > 0 else zone['low']
                outside = pen.low > boundary if direction > 0 else pen.high < boundary
                if pen.direction == -direction and outside:
                    self.candidate('B3' if direction > 0 else 'S3', pen, direction, boundary,
                                   {'ruleId': 'THIRD_POINT_STRICT_RETEST_V1', 'zoneStartIndex': zone['startIndex'],
                                    'zoneLow': zone['low'], 'zoneHigh': zone['high'],
                                    'departureStrokePosition': origin, 'pullbackStrokePosition': number,
                                    'referenceLessons': [20, 21]})
                zone['lifecycle'] = 'DEPARTED'
                self.active = self.departure = None
            else:
                if pen.b > zone['high']:
                    self.departure = (1, number)
                elif pen.b < zone['low']:
                    self.departure = (-1, number)
                else:
                    zone['endIndex'] = pen.end
        if self.active is None and len(self.pens) >= 3:
            chunk = self.pens[-3:]
            low, high = max(p.low for p in chunk), min(p.high for p in chunk)
            if low < high:
                zone = {'type': 'ZONE', 'startIndex': chunk[0].start, 'endIndex': pen.end,
                        'low': low, 'high': high, 'direction': 'RANGE', 'engineConfirmed': True,
                        'rawFlag': 'AIQUANT_THREE_SEALED_BI', 'lifecycle': 'ACTIVE',
                        'evidence': {'ruleId': 'THREE_BI_FIXED_CORE_ZONE_V1', 'basis': 'BI',
                                     'sourceStrokePositions': [number - 2, number - 1, number],
                                     'referenceLessons': [20]}}
                self.zones.append(zone)
                self.active = zone
        self.divergence(pen, number)
        self.second_points(pen, number)

    def divergence(self, pen, number):
        if number < 2:
            return
        previous = self.pens[-3]
        if previous.direction != pen.direction:
            return
        context = [z for z in self.zones if z['endIndex'] <= previous.start]
        if len(context) < 2:
            return
        left, right = context[-2:]
        trending = right['low'] > left['high'] if pen.direction > 0 else right['high'] < left['low']
        outside = min(previous.b, pen.b) > right['high'] if pen.direction > 0 else max(previous.b, pen.b) < right['low']
        old_area, new_area = self.area(previous), self.area(pen)
        if (not trending or not outside or pen.direction * (pen.b - previous.b) <= 0
                or old_area <= 0 or not new_area < old_area * PARAMETERS['divergenceAreaRatio']):
            return
        direction = -pen.direction
        point = self.candidate('B1' if direction > 0 else 'S1', pen, direction, pen.b,
                               {'ruleId': 'TREND_MACD_AREA_DIVERGENCE_V1', 'previousArea': old_area,
                                'currentArea': new_area, 'ratioLimit': PARAMETERS['divergenceAreaRatio'],
                                'sourceStrokePositions': [number - 2, number],
                                'trendZoneStarts': [left['startIndex'], right['startIndex']],
                                'referenceLessons': [24, 53]})
        if point:
            self.first_points[direction] = (number, point)

    def second_points(self, pen, number):
        for direction, (origin, first) in list(self.first_points.items()):
            if number != origin + 2 or first['signalState'] != 'CANDIDATE' or pen.direction != -direction:
                continue
            if direction * (pen.b - first['startPrice']) <= 0:
                continue
            self.candidate('B2' if direction > 0 else 'S2', pen, direction, first['invalidation'],
                           {'ruleId': 'SECOND_POINT_HIGHER_LOW_LOWER_HIGH_V1',
                            'firstPointIndex': first['startIndex'], 'firstPointType': first['signalType'],
                            'sourceStrokePositions': [origin, number], 'referenceLessons': [21, 53]})


class NativeEngine:
    def __init__(self):
        self.bars, self.sealed, self.fractals, self.turns, self.pens = [], [], [], [], []
        self.pending = None
        # Sealed objects are immutable. Materialize their wire representation
        # once, rather than rebuilding all historical evidence on every bar.
        self.fractal_records, self.pen_records, self.segment_records = [], [], []
        self.direction = 1
        self.segments = SegmentModel()
        self.histogram = []
        self.ema12 = self.ema26 = self.dea = None
        self.zones = ZoneSignalModel(self.bars, self.histogram)

    def push(self, bar):
        if bar['index'] != len(self.bars):
            raise ValueError('Native engine expects contiguous, append-only bars')
        if not all(math.isfinite(bar[k]) for k in ('open', 'high', 'low', 'close')):
            raise ValueError('Non-finite native candle')
        if not bar['low'] <= min(bar['open'],bar['close']) <= max(bar['open'],bar['close']) <= bar['high']:
            raise ValueError('Invalid native OHLC envelope')
        self.bars.append(dict(bar))
        close = bar['close']
        self.ema12 = close if self.ema12 is None else self.ema12 + (close - self.ema12) * 2 / 13
        self.ema26 = close if self.ema26 is None else self.ema26 + (close - self.ema26) * 2 / 27
        difference = self.ema12 - self.ema26
        self.dea = difference if self.dea is None else self.dea + (difference - self.dea) * 2 / 10
        self.histogram.append((difference - self.dea) * 2)
        self.zones.invalidate(bar)
        i = bar['index']
        candle = Merged(bar['high'], bar['low'], i, i, (i,))
        if self.pending is None:
            self.pending = candle
            return
        old = self.pending
        included = ((candle.high <= old.high and candle.low >= old.low)
                    or (candle.high >= old.high and candle.low <= old.low))
        if included:
            choose_high = candle.high >= old.high if self.direction > 0 else candle.high <= old.high
            choose_low = candle.low >= old.low if self.direction > 0 else candle.low <= old.low
            self.pending = Merged(candle.high if choose_high else old.high,
                                  candle.low if choose_low else old.low,
                                  i if choose_high else old.high_index, i if choose_low else old.low_index,
                                  old.indices + (i,))
            return
        self.direction = 1 if candle.high > old.high else -1
        self.sealed.append(old)
        self.pending = candle
        if len(self.sealed) < 3:
            return
        left, middle, right = self.sealed[-3:]
        top = middle.high > max(left.high, right.high) and middle.low > max(left.low, right.low)
        bottom = middle.low < min(left.low, right.low) and middle.high < min(left.high, right.high)
        if not top and not bottom:
            return
        fractal = Fractal(1 if top else -1, middle.high if top else middle.low,
                          middle.high_index if top else middle.low_index, len(self.sealed) - 2,
                          i, left.indices + middle.indices + right.indices)
        self.fractals.append(fractal)
        self.fractal_records.append(fractal_record(fractal))
        if not self.turns:
            self.turns.append(fractal)
        elif fractal.kind == self.turns[-1].kind:
            if fractal.kind * (fractal.price - self.turns[-1].price) > 0:
                self.turns[-1] = fractal
        elif (fractal.position - self.turns[-1].position >= PARAMETERS['minimumFractalCenterDistance']
              and fractal.kind * (fractal.price - self.turns[-1].price) > 0):
            self.turns.append(fractal)
            if len(self.turns) >= 3:
                a, b = self.turns[-3:-1]
                pen = Stroke(a.index, b.index, a.price, b.price, i)
                self.pens.append(pen)
                self.pen_records.append(primitive('BI', pen, evidence={'ruleId': 'SEALED_OPPOSITE_STROKE_V1',
                    'confirmedIndex': pen.observed, 'sourceStrokePosition': len(self.pens)-1, 'referenceLessons': [62]}))
                prior_segments = len(self.segments.segments)
                self.segments.push(pen)
                self.segment_records.extend(primitive('SEGMENT', segment, evidence=evidence)
                    for segment, evidence in zip(self.segments.segments[prior_segments:],self.segments.evidence[prior_segments:]))
                self.zones.push(pen)

    def structures(self):
        output = list(self.fractal_records)
        output.extend(self.pen_records)
        if len(self.turns) >= 2:
            a, b = self.turns[-2:]
            tail = Stroke(a.index, b.index, a.price, b.price, b.observed)
            output.append(primitive('BI', tail, False, evidence={'ruleId': 'DYNAMIC_STROKE_V1', 'referenceLessons': [62]}))
        output.extend(self.segment_records)
        if self.segments.initialized and self.segments.start < len(self.pens):
            pens = self.pens[self.segments.start:]
            origin = pens[0]
            endpoint = max(pens, key=lambda p: origin.direction * p.b)
            if origin.direction * (endpoint.b - origin.a) > 0:
                output.append(primitive('SEGMENT', Stroke(origin.start, endpoint.end, origin.a, endpoint.b, endpoint.observed),
                                        False, evidence={'ruleId': 'DYNAMIC_SEGMENT_V1', 'referenceLessons': [67]}))
        output.extend(dict(z) for z in self.zones.zones)
        output.extend(dict(s) for s in self.zones.signals)
        return output
