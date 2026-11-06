"""Frozen line/channel observations; live calculations never inspect future labels."""
import json,math,re,statistics
from functools import lru_cache
from pathlib import Path
from backtesting.line_geometry import geometry_snapshot
from backtesting.multifactor_features import extended_vector,stamp
from backtesting.outcome_features import matches


@lru_cache(maxsize=1)
def model():
    return json.loads((Path(__file__).resolve().parents[1]/'config/line-patterns.json').read_text(encoding='utf-8'))


def evaluate_lines(frame,previous,seconds,target='ALL',evidence='IMPROVED'):
    previous=previous or {};metadata=model()
    depth=frame.get('depth') or {};chart=frame.get('chart') or {};daily=frame.get('daily') or {}
    empty=(previous,[],{'status':'WARMING','message':'通道／趋势线模型需要600根完整15分钟柱、65根完整日线及有效自动线。'})
    if seconds!=900 or frame.get('assetType','FUTURE')!='FUTURE':return previous,[],{'status':'OUT_OF_SCOPE'}
    symbol=str(depth.get('symbol',''));root=re.match(r'^([A-Z]+)[0-9]',symbol.upper())
    if not root or root.group(1) not in metadata['universeCodes']:return previous,[],{'status':'OUT_OF_SCOPE'}
    if depth.get('dataStatus')!='FRESH':return empty
    if any(v.get('dataStatus')!='FRESH' or v.get('symbol')!=symbol for v in (chart,daily)):return empty
    minutes=(chart.get('points') or [])[:-1];days=(daily.get('points') or [])[:-1]
    if len(minutes)<600 or len(days)<65:return empty
    minutes=minutes[-600:]
    try:
        quote=depth['dataTimestamp'];bar=minutes[-1]['timestamp'];forming=chart['points'][-1]['timestamp'];daily_points=daily['points']
        if any(not 0<=stamp(quote)-stamp(v['dataTimestamp'])<=15 for v in (chart,daily)):return empty
        if stamp(forming)>stamp(quote) or stamp(minutes[-1]['timestamp'])<stamp(daily_points[-1]['timestamp']) or stamp(daily_points[-1]['timestamp'])>stamp(quote):return empty
        for series in (minutes,daily_points):
            for i,b in enumerate(series):
                if any(not isinstance(b[k],(int,float)) or isinstance(b[k],bool) or not math.isfinite(b[k]) for k in ('open','high','low','price','volume')):return empty
                if not 0<b['low']<=min(b['open'],b['price'])<=max(b['open'],b['price'])<=b['high'] or b['volume']<0:return empty
                if stamp(b['timestamp'])>stamp(quote) or i and stamp(series[i-1]['timestamp'])>=stamp(b['timestamp']):return empty
        if statistics.median(b['volume'] for b in days[-20:])<10000 or minutes[-1]['volume']<100:
            return previous,[],{'status':'OUT_OF_ACTIVITY_SCOPE'}
        geometry=geometry_snapshot(minutes,provisional=False)
        extended=extended_vector(minutes,days)
        if geometry.get('status')!='READY' or extended is None:return empty
        features={**extended['values'],**geometry['features']}
    except (KeyError,TypeError,ValueError,OverflowError):return empty
    patterns=[]
    for pattern in metadata['patterns']:
        if pattern.get('developmentSelected',True) is False:continue
        name=pattern['target'];category='ENTRY' if name.endswith('_ENTRY') else 'EXIT' if name.startswith('EXIT_') else 'TURN' if name.endswith('_TURN') else 'TREND'
        if target!='ALL' and target!=category:continue
        if evidence!='ALL' and not pattern['grade'].startswith(('PROBABILITY_LIFT_SUPPORTED','TENTATIVE_PROBABILITY_LIFT')):continue
        if matches(features,pattern['path']):patterns.append(pattern)
    state={'lastBar':bar,'modelVersion':metadata['version']}
    snapshot={'status':'READY','modelVersion':metadata['version'],'features':features,'geometry':geometry,
              'matchedPatterns':[p['id'] for p in patterns],
              'message':'通道／趋势线历史条件概率观察；自动线用此前已知数据固定后判断穿越，手动画线不参与。'}
    if (not previous.get('lastBar') or previous.get('modelVersion')!=metadata['version'] or previous['lastBar']==bar
            or not 0<=stamp(quote)-stamp(forming)<=15):return state,[],snapshot
    events=[]
    for pattern in patterns:
        events.append({'rule':'OUTCOME_PATTERN','variant':pattern['id'],'key':f'{metadata["version"]}:{pattern["id"]}:{bar}',
                       'label':pattern['label']+' · 通道／趋势线概率线索',
                       'evidence':{'opportunity':'HISTORICAL_PROBABILITY_WATCH','confirmation':'BAR_CLOSE','triggerSeconds':900,
                                   'modelVersion':metadata['version'],'patternId':pattern['id'],'targetDefinition':pattern['target'],
                                   'featureAt':bar,'confirmedAt':forming,'availableAt':quote,'referenceWindowStart':minutes[0]['timestamp'],
                                   'conditions':pattern['path'],'features':features,'geometry':geometry,
                                   'historicalStatistics':pattern['statistics'],'evidenceGrade':pattern['grade'],
                                   'containsChan':pattern.get('containsChan',False),'tradeQualified':False,
                                   'message':'自动拟合线不是确定支撑阻力；历史样本复用、候选与失败均保留，尚无新的前瞻盈利验证。'}})
    return state,events,snapshot
