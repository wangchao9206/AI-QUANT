"""Match learned historical patterns using present and past bars only, never future labels."""
import json,re,statistics
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from backtesting.outcome_features import vector,matches

@lru_cache(maxsize=1)
def model():
    return json.loads((Path(__file__).resolve().parents[1]/'config/outcome-patterns.json').read_text(encoding='utf-8'))
def stamp(s):return datetime.fromisoformat(s.replace('Z','+00:00')).timestamp()
def evaluate_outcome(frame,previous,seconds,target='ALL',evidence='IMPROVED'):
    previous=previous or {};metadata=model();depth=frame.get('depth',{});chart=frame.get('chart',{});daily=frame.get('daily') or {}
    empty=(previous,[],{'status':'WARMING','message':'概率模型需要真实的15分钟及已完成日线。'})
    if seconds!=900 or frame.get('assetType','FUTURE')!='FUTURE':return previous,[],{'status':'OUT_OF_SCOPE'}
    root=re.match(r'^([A-Z]+)[0-9]',str(depth.get('symbol','')).upper())
    if not root or root.group(1) not in metadata['universeCodes']:return previous,[],{'status':'OUT_OF_SCOPE'}
    if daily.get('dataStatus')!='FRESH' or daily.get('symbol')!=depth.get('symbol'):return empty
    minutes=(chart.get('points') or [])[:-1];days=(daily.get('points') or [])[:-1]
    if not minutes or len(days)<25:return empty
    try:
        daily_points=daily['points'];forming=chart['points'][-1]['timestamp'];bar=minutes[-1]['timestamp'];quote=depth['dataTimestamp']
        if not 0<=stamp(quote)-stamp(daily['dataTimestamp'])<=15 or stamp(minutes[-1]['timestamp'])<stamp(daily_points[-1]['timestamp']):return empty
        if any(stamp(a['timestamp'])>=stamp(b['timestamp']) for a,b in zip(daily_points,daily_points[1:])):return empty
        if stamp(daily_points[-1]['timestamp'])>stamp(quote):return empty
        if statistics.median(b['volume'] for b in days[-20:])<metadata['activityMedianDailyVolume20'] or minutes[-1]['volume']<100:return previous,[],{'status':'OUT_OF_ACTIVITY_SCOPE'}
        features=vector(minutes,days)
        if features is None:return empty
    except (TypeError,KeyError,ValueError):return empty
    state={'lastBar':bar};patterns=[]
    for pattern in metadata['patterns']:
        name=pattern['target'];category='ENTRY' if name in ('LONG_ENTRY','SHORT_ENTRY') else 'EXIT' if name.startswith('EXIT_') else 'TURN' if name.endswith('_TURN') else 'TREND'
        if target!='ALL' and target!=category:continue
        if (evidence=='ALL' or pattern['grade'].startswith(('PROBABILITY_LIFT_SUPPORTED','TENTATIVE_PROBABILITY_LIFT'))) and matches(features['values'],pattern['path']):patterns.append(pattern)
    snapshot={'status':'READY','modelVersion':metadata['version'],'features':features['values'],'matchedPatterns':[p['id'] for p in patterns],
        'message':'历史相似条件概率，不是当前确定结果；方向概率与成本后期望分别看。'}
    # No startup replay and no retrospective trigger when a recovered check missed the confirmation.
    if not previous.get('lastBar') or previous['lastBar']==bar or not 0<=stamp(quote)-stamp(forming)<=15:return state,[],snapshot
    events=[]
    for pattern in patterns:
        events.append({'rule':'OUTCOME_PATTERN','variant':pattern['id'],'key':f'OUTCOME_PATTERN:{pattern["id"]}:{bar}',
            'label':pattern['label']+' · 历史概率线索','evidence':{'opportunity':'HISTORICAL_PROBABILITY_WATCH',
                'confirmation':'BAR_CLOSE','triggerSeconds':900,'modelVersion':metadata['version'],'patternId':pattern['id'],
                'targetDefinition':pattern['target'],'featureAt':bar,'confirmedAt':forming,'availableAt':quote,
                'conditions':pattern['path'],'features':features['values'],'historicalStatistics':pattern['statistics'],
                'evidenceGrade':pattern['grade'],'tradeQualified':False,
                'message':'用过去已知特征匹配历史结果标签；拐点为未来形态的概率候选，当前没有使用未来K线。'}})
    return state,events,snapshot
