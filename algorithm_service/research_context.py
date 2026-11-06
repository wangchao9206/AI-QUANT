"""Descriptive daily context; research failure gates are never promoted to trade advice."""
import json
from functools import lru_cache
from pathlib import Path
from backtesting.trend_features import CONDITIONS,features

@lru_cache(maxsize=1)
def study():
    return json.loads((Path(__file__).resolve().parents[1]/'config/trend-study.json').read_text(encoding='utf-8'))

def alert_assessment(rule,period,seconds):
    if rule not in ('DAILY_MA_BREAKOUT_UP','DAILY_MA_BREAKOUT_DOWN','DAILY_MA_PULLBACK'):return None
    data=study().get('intradayStudy',{})
    key=None
    if seconds==900 and period==20:key={'DAILY_MA_BREAKOUT_UP':'CROSS_DAY20_UP','DAILY_MA_BREAKOUT_DOWN':'CROSS_DAY20_DOWN'}.get(rule)
    if seconds==900 and period==5 and rule=='DAILY_MA_BREAKOUT_DOWN':key='CROSS_DAY5_DOWN'
    if not key:return {'qualification':'NOT_VALIDATED_FOR_THIS_RULE','tradeQualified':False,
        'reason':'逐笔盘中触及不能用15分钟触及收回的代理验证替代。' if rule=='DAILY_MA_PULLBACK' else '参数或周期不在本次统计范围内。'}
    return {'studyId':data.get('studyId'),'qualification':'EXPLORATORY_NO_STABLE_EDGE','tradeQualified':False,
        'sampleScope':'EIGHT_CURRENT_CONTRACTS_RETROSPECTIVE','condition':key,**data.get('conditions',{}).get(key,{})}

def evaluate_context(daily,previous,valid,emit_allowed):
    previous=previous or {}
    if not valid or not daily:return {**previous,'pending':[]},[],{'status':'INSUFFICIENT_DAILY_DATA'}
    bars=daily.get('points',[])[:-1];values=features(bars)
    if values is None:return {**previous,'pending':[]},[],{'status':'INSUFFICIENT_DAILY_DATA'}
    reference=bars[-1]['timestamp'];report=study();pending=previous.get('pending',[]) if previous.get('reference')==reference else []
    if previous.get('reference') and previous['reference']!=reference:
        pending=[]
        for condition in values['conditions']:
            stats=report['conditions'][condition]
            pending.append({'rule':'DAILY_RESEARCH_CONTEXT','variant':condition,'key':f'DAILY_RESEARCH_CONTEXT:{condition}:{reference}',
                'label':CONDITIONS[condition][0]+' · 研究观察',
                'evidence':{'condition':condition,'confirmation':'DAILY_CLOSE_CONFIRMED','opportunity':'RESEARCH_OBSERVATION_ONLY',
                    'referencePeriod':'DAY','confirmationDay':reference,'features':values,'studyId':report['studyId'],
                    'pivotAt':bars[-3]['timestamp'] if condition in ('LOW_PIVOT','HIGH_PIVOT') else None,
                    'pivotPrice':bars[-3]['low' if condition=='LOW_PIVOT' else 'high'] if condition in ('LOW_PIVOT','HIGH_PIVOT') else None,
                    'rightCompleteBars':2 if condition in ('LOW_PIVOT','HIGH_PIVOT') else None,
                    'qualification':report['qualification'],'studyDirection':CONDITIONS[condition][1],'historicallyConsistent':stats['historicallyConsistent'],
                    'developmentSelectedHorizon':stats['developmentSelectedHorizon'],'historicalStats':stats['selected'],
                    'scope':'DAILY_ONLY_NOT_15M_OR_INTRABAR_VALIDATION'}})
    state={'reference':reference,'pending':[] if emit_allowed else pending}
    context={'status':'READY','studyId':report['studyId'],'qualification':report['qualification'],'regime':values['regime'],
        'features':values,'referenceAt':reference,'conditions':[{ 'code':k,**report['conditions'][k]} for k in values['conditions']],
        'message':'本批条件未通过跨时段稳健性门槛；仅作趋势／拐点观察，不是已验证入场优势。'}
    return state,pending if emit_allowed else [],context
