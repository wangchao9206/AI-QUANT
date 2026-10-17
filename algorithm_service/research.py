"""Research evidence and account-risk scenarios. Never places an order."""
from __future__ import annotations

import hashlib
import json
import math
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import HTTPException
from pydantic import ConfigDict, Field

from algorithm_service.models import ApiModel
from config.settings import settings
from data.live_feed import SHANGHAI
from data.data_feed import KLineBar
from data.trading_day import completed_daily_bar
from engines.empirical_engines import _atr


class PlanRequest(ApiModel):
    model_config = ConfigDict(allow_inf_nan=False)
    symbol: str = Field(pattern=r"^[A-Za-z]{1,4}[A-Za-z0-9]{0,8}$")
    mode: Literal['EMPIRICAL', 'CULTURAL_COMPARE'] = 'EMPIRICAL'
    expected_contract: str | None = None
    equity: float = Field(default=1_000_000, gt=0, le=1e12)
    risk_pct: float = Field(default=1, gt=0, le=100)
    margin_budget_pct: float = Field(default=30, gt=0, le=100)
    max_leverage: float = Field(default=2, gt=0, le=20)
    daily_loss_limit_pct: float = Field(default=2, gt=0, le=100)
    daily_loss: float = Field(default=0, ge=0, le=1e12)
    total_risk_limit_pct: float = Field(default=3, gt=0, le=100)
    other_risk: float = Field(default=0, ge=0, le=1e12)
    other_margin: float = Field(default=0, ge=0, le=1e12)
    other_notional: float = Field(default=0, ge=0, le=1e13)
    position_side: Literal['FLAT', 'LONG', 'SHORT'] = 'FLAT'
    existing_lots: int = Field(default=0, ge=0, le=1_000_000)
    entry_price: float | None = Field(default=None, gt=0, le=1e9)
    stop_price: float | None = Field(default=None, gt=0, le=1e9)
    target_price: float | None = Field(default=None, gt=0, le=1e9)
    fee_rate: float = Field(default=.0001, ge=0, le=.01)
    margin_rate: float = Field(default=.12, gt=0, le=1)
    slippage_ticks: float = Field(default=1, ge=0, le=100)


def evidence_modes(prediction: dict) -> dict:
    empirical = prediction['dimensions']
    culture = prediction.get('cultural_references', [])
    available = lambda d: d.get('included_in_score') and d.get('score') is not None and d.get('confidence') is not None
    configured = sum(d['weight'] for d in empirical)
    used = sum(d['weight'] for d in empirical if available(d))
    modes = {}
    for name, dimensions in [('EMPIRICAL', empirical), ('CULTURAL_COMPARE', empirical + culture)]:
        eligible = [d for d in dimensions if available(d)]
        total = sum(d['weight'] for d in eligible)
        score = sum(d['weight'] * d['score'] for d in eligible) / total if total else 0
        resonance = max(sum(d['direction'] == side for d in eligible) for side in ['BULLISH','BEARISH']) / len(eligible) if eligible else 0
        signal = ('BUY' if score >= 25 else 'SELL' if score <= -25 else 'HOLD') if total else 'UNAVAILABLE'
        modes[name] = {'score': round(score, 1), 'signal': signal, 'resonance': round(resonance, 3),
            'empiricalCoverage': round(used / configured, 4) if configured else 0,
            'availableDimensions': sum(available(d) for d in empirical), 'totalDimensions': len(empirical),
            'culturalEffectiveWeight': round(sum(d['weight'] for d in culture if available(d)) / total, 4) if total and name=='CULTURAL_COMPARE' else 0,
            'missing': [d['name'] for d in empirical if not available(d)],
            'confidenceMeaning': '指标内部置信评分未经胜率校准，不作为盈利概率',
            'calibratedWinRate': None}
    return modes


def risk_scenario(context: dict, request: PlanRequest) -> dict:
    q = context.get('execution', {}).get('quote') or {}
    mode = context['modes'][request.mode]
    contract = context.get('execution', {}).get('contract')
    if request.expected_contract and contract != request.expected_contract:
        raise HTTPException(409, '实际交割合约已变化，请刷新研究资料后重新核算')
    if (request.position_side == 'FLAT') != (request.existing_lots == 0):
        raise HTTPException(422, '空仓时已有手数必须为 0；持仓时须填写正整数手数')
    missing = [key for key in ['volumeMultiple','priceTick','marginPerLot','commissionPerLot'] if q.get(key) is None]
    if missing:
        raise HTTPException(503, '真实交割合约规格未齐全，暂不估算手数：' + ', '.join(missing))
    mult, tick = float(q['volumeMultiple']), float(q['priceTick'])
    if mult <= 0 or tick <= 0 or q['marginPerLot'] <= 0 or q['commissionPerLot'] < 0:
        raise HTTPException(503, '真实合约规格无效，暂不估算手数')
    direction = 1 if mode['signal']=='BUY' else -1 if mode['signal']=='SELL' else 0
    held_direction = 1 if request.position_side=='LONG' else -1 if request.position_side=='SHORT' else 0
    scenario_direction = held_direction or direction
    entry = request.entry_price or float(q['price'])
    if scenario_direction:
        entry = (math.ceil(entry/tick-1e-10) if scenario_direction>0 else math.floor(entry/tick+1e-10))*tick
    atr = context.get('atr')
    stop = request.stop_price
    if stop is None and atr and scenario_direction:
        stop = entry - scenario_direction * 2 * atr
    if stop is not None:
        stop = (math.floor(stop / tick + 1e-10) if scenario_direction > 0 else math.ceil(stop / tick - 1e-10)) * tick
    if scenario_direction and stop is not None and (entry-stop)*scenario_direction <= 0:
        raise HTTPException(422, '止损须位于风险方向：多头止损低于入场价，空头止损高于入场价')
    if stop is not None and stop <= 0:
        raise HTTPException(422, '止损价必须为正数，请手动设置有效价位')
    target = request.target_price
    if target is None and stop is not None and scenario_direction:
        target = entry + scenario_direction * abs(entry-stop) * 2.5
    if target is not None:
        target = round(target / tick) * tick
        if target <= 0 or scenario_direction and (target-entry)*scenario_direction <= 0:
            raise HTTPException(422, '目标价须位于预期盈利方向且为正数')
    per_lot_fee = max(float(q['commissionPerLot']), entry*mult*request.fee_rate,
                      (stop or entry)*mult*request.fee_rate)
    friction = 2 * per_lot_fee + 2 * request.slippage_ticks * tick * mult
    unit_risk = abs(entry-stop)*mult + friction if stop is not None and scenario_direction else None
    available_risk = max(0, min(request.equity*request.risk_pct/100,
        request.equity*request.daily_loss_limit_pct/100-request.daily_loss,
        request.equity*request.total_risk_limit_pct/100-request.other_risk))
    available_margin = max(0, min(request.equity, request.equity*request.margin_budget_pct/100)-request.other_margin)
    available_notional = max(0, request.equity*request.max_leverage-request.other_notional)
    margin_per_lot = max(float(q['marginPerLot']), entry*mult*request.margin_rate)
    notional_per_lot = entry * mult
    limits = {'risk': math.floor(available_risk/unit_risk) if unit_risk else 0,
              'margin': math.floor(available_margin/(margin_per_lot+per_lot_fee)),
              'leverage': math.floor(available_notional/notional_per_lot)}
    max_lots = max(0, min(limits.values()))
    state = context['execution'].get('marketState', 'UNKNOWN')
    gates = []
    if state != 'LIVE': gates.append({'CLOSED_CACHE':'休市缓存：可准备计划，当前不产生开仓动作',
        'STALE':'交易时段行情已过期：暂停新增计划', 'DISCONNECTED':'行情连接中断：暂停新增计划',
        'WARMING':'真实交割合约行情正在采集', 'UNKNOWN':'交易时段状态尚未确认'}.get(state, '行情未就绪'))
    if mode['empiricalCoverage'] < .6: gates.append('实证证据覆盖不足 60%：暂停新增计划')
    if available_risk <= 0: gates.append('单笔、单日或总风险预算已耗尽')
    if max_lots == 0 and scenario_direction: gates.append('当前条件下不足以承担 1 手风险、保证金或名义敞口')
    if request.entry_price:
        for field, compare in [('upperLimit', lambda v: entry>v), ('lowerLimit',lambda v: entry<v)]:
            if q.get(field) and compare(q[field]): gates.append('情景入场价超出当前涨跌停范围')
    reduce_lots = max(0, request.existing_lots-max_lots)
    if state in ('STALE','DISCONNECTED','WARMING','UNKNOWN') or mode['empiricalCoverage'] < .6:
        action, message = 'PREPARE', '先更新资料并核对持仓，当前仅保留风险试算'
    elif reduce_lots:
        action, message = 'REDUCE', f'已有持仓超出所填风险约束，评估减少 {reduce_lots} 手'
    elif held_direction and direction and held_direction != direction:
        action, message = 'REVIEW_EXIT', '原持仓与研究方向相反，先制定退出计划'
    elif mode['signal']=='HOLD':
        action, message = ('HOLD_POSITION','持仓观察，沿用已确认的保护条件') if held_direction else ('WAIT','空仓等待，不新增仓位')
    elif gates:
        action, message = 'PREPARE', '保留为研究情景，待交易时段与证据条件满足后重新核算'
    else:
        action, message = 'CONDITIONAL_ENTRY', '研究方向成立时才考虑新增；需人工确认价格与成交条件'
    new_lots = max(0,max_lots-request.existing_lots) if action=='CONDITIONAL_ENTRY' else 0
    return {'planId':str(uuid.uuid4()), 'createdAt':datetime.now(SHANGHAI).isoformat(),
        'symbol':context['symbol'], 'contract':contract, 'mode':request.mode, 'modeEvidence':mode,
        'modelVersion':context['modelVersion'], 'dataTimestamp':q.get('dataTimestamp'),
        'marketState':state,'action':action,'actionMessage':message,'gates':gates,
        'entryPrice':entry,'stopPrice':stop,'targetPrice':target,
        'scenarioDirection':'LONG' if scenario_direction>0 else 'SHORT' if scenario_direction<0 else 'NONE',
        'maxLots':max_lots,'newLots':new_lots,'reduceLots':reduce_lots,'limits':limits,
        'riskPerLot':round(unit_risk,2) if unit_risk else None,'frictionPerLot':round(friction,2),
        'riskBudget':round(available_risk,2), 'plannedLoss':round((unit_risk or 0)*max_lots,2),
        'existingPositionRisk':round((unit_risk or 0)*request.existing_lots,2),
        'marginRequired':round(margin_per_lot*max_lots,2),
        'marginPct':round((margin_per_lot*max_lots+request.other_margin)/request.equity*100,2),
        'notionalLeverage':round((notional_per_lot*max_lots+request.other_notional)/request.equity,3),
        'lossPct':round((unit_risk or 0)*max_lots/request.equity*100,3),
        'holdingHorizon':'日线研究 · 未来 1–5 个交易日观察，每个交易日重新核算',
        'validity':'仅适用于本次合约、数据时间与账户参数；行情、合约或风险输入变化后需重算',
        'trigger':f"所选模式评分{'≥25' if direction>0 else '≤-25'}、实证覆盖至少 60% 且行情有效时，按交割合约情景价 {entry:g} 核验成交条件" if direction else '等待所选模式达到方向阈值，当前不建立新仓',
        'invalidation':f"{'跌破' if scenario_direction>0 else '突破'}保护价 {stop:g}，或信号反向、预算超限时重新评估" if stop else '证据不足或行情异常时暂停新增',
        'assumptions':['手动输入的账户情景，不读取或操作实盘账户',
            '止损损失为价差、双边手续费与不利滑点估算；跳空、涨跌停或流动性不足时可能超出',
            '保证金、手续费采用当前观测规格；期货公司额外加收未自动取得',
            f"默认保护距离使用{context.get('atrBasis','日线 ATR(14)')}的 2 倍，仅作波动尺度；入场与估值采用交割合约价格"],
        'inputs':request.model_dump(by_alias=True),'researchContext':context}


class ResearchService:
    def __init__(self, predictions):
        self.predictions = predictions
        self.cache = {}

    def context(self, symbol: str, trace: str, refresh=False):
        cached = self.cache.get(symbol)
        if cached and not refresh and time.monotonic()-cached[0] < 10:
            return cached[1]
        feed = self.predictions.market_feed
        resolver = getattr(feed,'provider_symbol',None)
        provider = resolver(symbol) if resolver else None
        if provider:
            from data.tqsdk_feed import canonical_symbol
            symbol = canonical_symbol(provider)
        prediction = self.predictions.predict(symbol,trace)
        execution_reader = getattr(feed,'execution_snapshot',None)
        execution = execution_reader(symbol) if execution_reader else {'marketState':'UNKNOWN','contract':None,'quote':None}
        _, bars, _ = feed.prediction_inputs(symbol)
        atr_basis='主连日线 ATR(14)（交割月日线暖机时的替代尺度）' if symbol.endswith('M') else '交割合约日线 ATR(14)'
        if len(execution.get('history',[]))>=20:
            bars=[KLineBar(datetime.fromisoformat(b['timestamp']),b['open'],b['high'],b['low'],
                b['price'],b['volume'],b['openInterest']) for b in execution['history']]
            atr_basis='实际交割合约已完成日线 ATR(14)'
        execution.pop('history',None)
        bars=[bar for bar in bars if completed_daily_bar(bar.timestamp)]
        atr = _atr(bars) if len(bars)>=20 else None
        events=[]
        q=execution.get('quote') or {}
        if q.get('expiryTimestamp'):
            expiry=datetime.fromtimestamp(q['expiryTimestamp'],SHANGHAI)
            days=(expiry.date()-datetime.now(SHANGHAI).date()).days
            events.append({'type':'EXPIRY','label':f'观测到期日 {expiry:%Y-%m-%d} · 剩余 {days} 个自然日', 'urgent':days<=15})
        for key,label in [('upperLimit','涨停价'),('lowerLimit','跌停价')]:
            value=q.get(key)
            if value:
                distance=abs(value-q['price'])/q['price']*100
                events.append({'type':key,'label':f'{label} {value:g} · 距现价 {distance:.2f}%', 'urgent':distance<1})
        result={'symbol':symbol,'modelVersion':settings.version,'signalTimestamp':prediction['data_timestamp'],
            'execution':execution,'atr':atr,'atrBasis':atr_basis,
            'modes':evidence_modes(prediction),'events':events,'traceId':trace,
            'dimensionNote':'动量、技术指标、持仓、流动性等多项复用行情输入；方向一致性不等于独立证据或胜率。'}
        if len(self.cache)>128:self.cache.clear()
        self.cache[symbol]=(time.monotonic(),result)
        return result


def engine_fingerprint() -> str:
    root=Path(__file__).resolve().parents[1]
    digest=hashlib.sha256()
    for pattern in ['engines/*.py','backtesting/*.py','config/settings.py','data/tqsdk_backtest.py','data/trading_day.py']:
        for path in sorted(root.glob(pattern)):
            digest.update(str(path.relative_to(root)).replace('\\','/').encode())
            digest.update(path.read_bytes().replace(b'\r\n',b'\n'))
    return digest.hexdigest()


def validation_snapshot():
    path=Path(os.getenv('HISTORY_CACHE_DIR','data/history'))/'validation/research-validation.json'
    if not path.exists():
        return {'status':'NOT_RUN','profitabilityValidated':False,'message':'尚无可审计的历史验证报告','strategies':[]}
    try:
        report=json.loads(path.read_text(encoding='utf-8'))
        matches=report.get('engineFingerprint')==engine_fingerprint() and report.get('modelVersion')==settings.version
        return {**report,'status':'RETROSPECTIVE_CHECKED' if matches else 'NEEDS_RECHECK',
                'profitabilityValidated':False,'currentModelVersion':settings.version}
    except (ValueError,OSError):
        return {'status':'UNAVAILABLE','profitabilityValidated':False,'message':'验证报告读取失败','strategies':[]}
