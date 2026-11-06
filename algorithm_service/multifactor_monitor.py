"""Research-grade multi-period/Chan probability observations, no future label calls."""
import json,re,statistics
from functools import lru_cache
from pathlib import Path
from backtesting.multifactor_features import extended_vector,stamp
from backtesting.outcome_features import matches

@lru_cache(maxsize=1)
def model():
    return json.loads((Path(__file__).resolve().parents[1]/'config/multifactor-patterns.json').read_text(encoding='utf-8'))

def evaluate_multifactor(frame,previous,seconds,target='ALL',evidence='IMPROVED',family='COMBINED'):
    previous=previous or {};metadata=model();depth=frame.get('depth',{});chart=frame.get('chart',{});daily=frame.get('daily') or {}
    empty=(previous,[],{'status':'WARMING','message':'多周期／缠论模型需要600根完整15分钟柱和65根完整日线。'})
    if seconds!=900 or frame.get('assetType','FUTURE')!='FUTURE':return previous,[],{'status':'OUT_OF_SCOPE'}
    root=re.match(r'^([A-Z]+)[0-9]',str(depth.get('symbol','')).upper())
    if not root or root.group(1) not in metadata['universeCodes']:return previous,[],{'status':'OUT_OF_SCOPE'}
    if depth.get('dataStatus')!='FRESH':return empty
    if any(v.get('dataStatus')!='FRESH' or v.get('symbol')!=depth.get('symbol') for v in (chart,daily)):return empty
    minutes=(chart.get('points') or [])[:-1];days=(daily.get('points') or [])[:-1]
    if len(minutes)<600 or len(days)<65:return empty
    try:
        quote=depth['dataTimestamp'];bar=minutes[-1]['timestamp'];forming=chart['points'][-1]['timestamp'];daily_points=daily['points']
        if not 0<=stamp(quote)-stamp(daily['dataTimestamp'])<=15:return empty
        if not 0<=stamp(quote)-stamp(chart['dataTimestamp'])<=15:return empty
        if stamp(forming)>stamp(quote):return empty
        if stamp(minutes[-1]['timestamp'])<stamp(daily_points[-1]['timestamp']) or stamp(daily_points[-1]['timestamp'])>stamp(quote):return empty
        if any(stamp(a['timestamp'])>=stamp(b['timestamp']) for a,b in zip(daily_points,daily_points[1:])):return empty
        for b in days[-65:]:
            if not 0<b['low']<=min(b['open'],b['price'])<=max(b['open'],b['price'])<=b['high'] or b['volume']<0:return empty
        if statistics.median(b['volume'] for b in days[-20:])<10000 or minutes[-1]['volume']<100:return previous,[],{'status':'OUT_OF_ACTIVITY_SCOPE'}
        features=extended_vector(minutes,days)
        if features is None:return empty
    except (TypeError,KeyError,ValueError,OverflowError):return empty
    patterns=[]
    for pattern in metadata['patterns']:
        if pattern['family']!=family:continue
        name=pattern['target'];category='ENTRY' if name.endswith('_ENTRY') else 'EXIT' if name.startswith('EXIT_') else 'TURN' if name.endswith('_TURN') else 'TREND'
        if target!='ALL' and target!=category:continue
        if evidence!='ALL' and not pattern['grade'].startswith(('PROBABILITY_LIFT_SUPPORTED','TENTATIVE_PROBABILITY_LIFT')):continue
        if matches(features['values'],pattern['path']):patterns.append(pattern)
    state={'lastBar':bar,'modelVersion':metadata['version']}
    snapshot={'status':'READY','modelVersion':metadata['version'],'features':features['values'],'family':family,
              'contextBars':features['contextBars'],'matchedPatterns':[p['id'] for p in patterns],
              'message':'多周期／缠论历史条件概率观察；复用既有历史样本，尚无全新前瞻验证。'}
    if (not previous.get('lastBar') or previous.get('modelVersion')!=metadata['version'] or previous['lastBar']==bar
            or not 0<=stamp(quote)-stamp(forming)<=15):return state,[],snapshot
    events=[]
    for pattern in patterns:
        events.append({'rule':'OUTCOME_PATTERN','variant':pattern['id'],'key':f'{metadata["version"]}:{pattern["id"]}:{bar}',
                       'label':pattern['label']+' · 多周期／缠论概率线索',
                       'evidence':{'opportunity':'HISTORICAL_PROBABILITY_WATCH','confirmation':'BAR_CLOSE','triggerSeconds':900,
                                   'modelVersion':metadata['version'],'patternId':pattern['id'],'family':family,
                                   'targetDefinition':pattern['target'],'featureAt':bar,'confirmedAt':forming,'availableAt':quote,
                                   'conditions':pattern['path'],'features':features['values'],'contextBars':features['contextBars'],
                                   'chanProfile':features['chanProfile'],'containsChan':pattern['containsChan'],
                                   'historicalStatistics':pattern['statistics'],'withoutChanStatistics':pattern.get('withoutChanStatistics'),
                                   'evidenceGrade':pattern['grade'],'tradeQualified':False,
                                   'message':'缠论为具名研究实现，候选按确认时点使用；概率改善不等于盈利，样本复用尚需新的前瞻验证。'}})
    return state,events,snapshot
