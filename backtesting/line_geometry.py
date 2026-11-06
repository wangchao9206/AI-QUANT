"""Past-only price geometry for charts and registered probability experiments.

Every boundary is fitted before the currently evaluated closed bar. The same
frozen line is evaluated at previous/current prices to detect a crossing.
"""
import math
from datetime import datetime

VERSION = 'line-geometry-v1'


def _close(bar):
    return bar.get('price', bar.get('close'))


def _stamp(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()


def geometry_snapshot(points, provisional=True):
    """Indices address the original points; line extensions are projections only."""
    empty = {'version': VERSION, 'status': 'WARMING', 'asOf': None, 'lines': [], 'features': {},
             'message': '自动线需要至少61根完整OHLC柱；拟合不包含当前被评价柱。'}
    if not isinstance(points, list):
        return {**empty, 'status': 'INVALID'}
    closed = points[:-1] if provisional else points
    if len(closed) < 61:
        return empty
    # Only the fixed study window is used; older malformed history cannot alter it.
    start = max(0, len(closed)-121)
    try:
        for i in range(start, len(points)):
            b = points[i]
            values = [b['open'], b['high'], b['low'], _close(b)]
            if any(not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) for v in values):
                return {**empty, 'status': 'INVALID'}
            if any(abs(v)>1e100 for v in values):
                return {**empty, 'status': 'INVALID', 'message':'价格超出安全数值范围，暂停几何计算。'}
            if not 0 < b['low'] <= min(b['open'], _close(b)) <= max(b['open'], _close(b)) <= b['high']:
                return {**empty, 'status': 'INVALID'}
            timestamp = _stamp(b['timestamp'])
            if i > start and timestamp <= _stamp(points[i-1]['timestamp']):
                return {**empty, 'status': 'INVALID'}
    except (KeyError, TypeError, ValueError, OverflowError):
        return {**empty, 'status': 'INVALID'}
    current_index = len(closed)-1
    previous_index = current_index-1
    endpoint = len(points)-1
    current, previous = _close(closed[-1]), _close(closed[-2])
    fit_start = current_index-60
    fit = closed[fit_start:current_index]
    y = [_close(b) for b in fit]
    mean = sum(y)/60
    variance_x = sum((i-29.5)**2 for i in range(60))
    slope = sum((i-29.5)*(v-mean) for i, v in enumerate(y))/variance_x
    intercept = mean-slope*29.5
    sigma = math.sqrt(sum((v-(intercept+slope*i))**2 for i, v in enumerate(y))/60)
    prior = closed[:-1]
    volatility = prior[-15:]
    ranges = [max(b['high']-b['low'], abs(b['high']-_close(volatility[i])), abs(b['low']-_close(volatility[i])))
              for i, b in enumerate(volatility[1:])]
    atr = sum(ranges[-14:])/14
    if not all(math.isfinite(v) for v in (atr,slope,intercept,sigma)):
        return {**empty, 'status': 'INVALID'}
    if atr <= 0:
        return {**empty, 'message':'此前14根完整柱没有价格波动，无法进行ATR归一；等待有效窗口。'}
    features = {'line.channelKnown': 1, 'line.supportKnown': 0, 'line.resistanceKnown': 0,
                'line.slopeATR': slope/atr, 'line.widthATR': 4*sigma/atr, 'line.atr': atr,
                'line.fitR2': 1-sum((v-(intercept+slope*i))**2 for i,v in enumerate(y))/sum((v-mean)**2 for v in y)
                if any(v != mean for v in y) else 0}
    lines = []
    known_at = closed[-1]['timestamp']  # Next bar start proves the fitted final bar closed.

    def add(identifier, kind, label, first, value_first, line_slope, evidence):
        def at(index):
            return value_first+line_slope*(index-first)
        lines.append({'id': identifier, 'kind': kind, 'label': label, 'startIndex': first, 'endIndex': endpoint,
                      'startPrice': value_first, 'endPrice': at(endpoint), 'knownAt': known_at,
                      'startTimestamp': points[first]['timestamp'], 'endTimestamp': points[endpoint]['timestamp'],
                      'referenceWindowStart': points[start]['timestamp'],
                      'evidence': evidence})
        return at

    for suffix, kind, label, offset in (
        ('Center', 'REGRESSION_CENTER', '前60柱回归中线', 0),
        ('Upper', 'REGRESSION_UPPER', '回归通道上轨（2倍残差标准差）', 2*sigma),
        ('Lower', 'REGRESSION_LOWER', '回归通道下轨（2倍残差标准差）', -2*sigma),
    ):
        at = add('regression'+suffix, kind, label, fit_start, intercept+offset, slope,
                 {'fitBars': 60, 'fitStartAt': fit[0]['timestamp'], 'fitEndAt': fit[-1]['timestamp'],
                  'residualStd': sigma, 'slopePerBar': slope, 'excludesEvaluatedBar': True})
        features['line.channel'+suffix+'DistanceATR'] = (current-at(current_index))/atr
        features['line.channel'+suffix+'CrossUp'] = int(previous <= at(previous_index) and current > at(current_index))
        features['line.channel'+suffix+'CrossDown'] = int(previous >= at(previous_index) and current < at(current_index))

    lookback = prior[-20:]
    for suffix, kind, label, price in (
        ('RangeHigh', 'HORIZONTAL_RESISTANCE', '此前20柱高点阻力', max(b['high'] for b in lookback)),
        ('RangeLow', 'HORIZONTAL_SUPPORT', '此前20柱低点支撑', min(b['low'] for b in lookback)),
    ):
        at = add(suffix, kind, label, current_index-20, price, 0,
                 {'fitBars':20, 'excludesEvaluatedBar':True})
        features['line.'+suffix[0].lower()+suffix[1:]+'DistanceATR'] = (current-price)/atr
        features['line.'+suffix[0].lower()+suffix[1:]+'CrossUp'] = int(previous<=price and current>price)
        features['line.'+suffix[0].lower()+suffix[1:]+'CrossDown'] = int(previous>=price and current<price)

    pivot_start = max(0, current_index-120)
    for name, key, kind, label, direction in (
        ('support', 'low', 'TREND_SUPPORT', '已确认低点支撑斜线', -1),
        ('resistance', 'high', 'TREND_RESISTANCE', '已确认高点阻力斜线', 1),
    ):
        pivots = []
        for i in range(pivot_start+2, current_index-2):
            price=closed[i][key]
            if all(direction*price > direction*closed[j][key] for j in (i-2,i-1,i+1,i+2)):
                pivots.append(i)
        if len(pivots)<2:
            continue
        last=pivots[-1]
        first=next((i for i in reversed(pivots[:-1]) if last-i>=5),None)
        if first is None:
            continue
        first_price,last_price=closed[first][key],closed[last][key]
        pivot_slope=(last_price-first_price)/(last-first)
        at=add(name,kind,label,first,first_price,pivot_slope,
               {'anchors':[{'index':i,'timestamp':closed[i]['timestamp'],'price':closed[i][key],
                            'confirmedAt':closed[i+3]['timestamp']} for i in (first,last)],
                'rightConfirmationBars':2,'minimumAnchorDistance':5,'excludesEvaluatedBar':True})
        # The latest required right-side candle was complete before evaluated bar.
        lines[-1]['knownAt']=closed[last+3]['timestamp']
        features['line.'+name+'Known']=1
        features['line.'+name+'DistanceATR']=(current-at(current_index))/atr
        features['line.'+name+'SlopeATR']=pivot_slope/atr
        features['line.'+name+'CrossUp']=int(previous<=at(previous_index) and current>at(current_index))
        features['line.'+name+'CrossDown']=int(previous>=at(previous_index) and current<at(current_index))
    return {'version': VERSION, 'status':'READY','asOf':closed[-1]['timestamp'],'lines':lines,'features':features,
            'message':'自动线仅由当时已知历史计算；通道延伸是几何投影，不是价格预测。'}
