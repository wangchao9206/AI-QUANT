"""Bounded, stateless paper-strategy API inputs and market-context adapters."""
from datetime import datetime
from typing import Literal
import math

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from config.settings import settings
from data.data_feed import KLineBar
from data.trading_day import completed_daily_bar
from data.live_feed import SHANGHAI, root_symbol
from backtesting.strategy_signals import STRATEGY_NAMES, daily_signal, daily_atr

StrategyId = Literal['HOLISTIC_14D','MOMENTUM_BREAKOUT','BOLLINGER_REVERSAL','DUAL_THRUST','ADAPTIVE_CTA','BUY_AND_HOLD','WORKFLOW']
STRATEGY_VERSION = 'paper-daily-v1'


class SignalBar(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=lambda s: ''.join(
        [s.split('_')[0]]+[p.title() for p in s.split('_')[1:]]))
    timestamp: datetime
    open: float = Field(gt=0, allow_inf_nan=False)
    high: float = Field(gt=0, allow_inf_nan=False)
    low: float = Field(gt=0, allow_inf_nan=False)
    close: float = Field(gt=0, allow_inf_nan=False)
    volume: int = Field(ge=0)
    open_interest: int = Field(default=0, ge=0)
    contract: str | None = Field(default=None, max_length=16)

    @field_validator('timestamp')
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None: raise ValueError('日线时间必须包含时区')
        return value

    def bar(self):
        if not self.low <= min(self.open,self.close) <= max(self.open,self.close) <= self.high:
            raise HTTPException(422, '日线OHLC关系无效')
        return KLineBar(self.timestamp,self.open,self.high,self.low,self.close,self.volume,self.open_interest,self.contract)


class StrategyRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    strategy: StrategyId
    symbol: str = Field(pattern=r'^[A-Z]{1,4}[A-Z0-9]{0,8}$')
    as_of: datetime = Field(alias='asOf')
    bars: list[SignalBar] = Field(max_length=5000)
    execution_bars: list[SignalBar] = Field(default_factory=list, alias='executionBars', max_length=5000)
    direction: Literal[-1,0,1] = 0
    first_entry: bool = Field(default=True, alias='firstEntry')
    workflow: dict | None = None

    @field_validator('as_of')
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None: raise ValueError('决策时点必须包含时区')
        return value


def evaluate(request: StrategyRequest):
    def visible(rows):
        bars=[row.bar() for row in rows if row.timestamp <= request.as_of]
        if any(a.timestamp >= b.timestamp for a,b in zip(bars,bars[1:])):
            raise HTTPException(422, '日线必须严格按时间排序且不能重复')
        return bars
    bars=visible(request.bars)
    execution=visible(request.execution_bars)
    if request.strategy!='WORKFLOW' and request.workflow is not None:raise HTTPException(422,'仅工作流策略可携带工作流定义')
    try:
        result=daily_signal(request.strategy,bars,request.direction,request.symbol,first_entry=request.first_entry,workflow=request.workflow)
    except ValueError as exc:raise HTTPException(422,'工作流无效：'+str(exc)[:600]) from exc
    return {'strategy':request.strategy,'strategyName':'策略工作流' if request.strategy=='WORKFLOW' else STRATEGY_NAMES[request.strategy],
        'modelVersion':'workflow-daily-v1' if request.strategy=='WORKFLOW' else STRATEGY_VERSION,'signal':result.signal,'reason':result.reason,
        'signalTime':bars[-1].timestamp if bars else None,'historyCount':len(bars),
        'requiredBars':result.required_bars,'atr':daily_atr(execution,contract_aware=True) if execution else 0,
        'signalBasis':'OBSERVED_CONTINUOUS_DAILY','riskBasis':'OBSERVED_DELIVERY_DAILY',
        'nodeTrace':result.node_trace or []}


def live_context(feed, symbol: str):
    resolver=getattr(feed,'provider_symbol',None)
    provider=resolver(symbol) if resolver else None
    if provider:
        from data.tqsdk_feed import canonical_symbol
        symbol=canonical_symbol(provider)
    reader=getattr(feed,'execution_snapshot',None)
    if reader is None: raise HTTPException(503,'实时仿真需要天勤合约规格与交易时段状态')
    context=reader(symbol)
    contract=context.get('contract')
    quote=context.get('quote')
    if not contract or not quote or not math.isfinite(float(quote.get('price',0))) or float(quote.get('price',0))<=0:
        raise HTTPException(503,'实际交割合约行情尚在采集，请稍后刷新；历史回放可独立使用')
    required=['volumeMultiple','priceTick','marginPerLot','commissionPerLot']
    if any(quote.get(key) is None for key in required):
        raise HTTPException(503,'真实合约规格尚未就绪，请稍后刷新')
    now=datetime.fromisoformat(context['checkedAt'])
    # The feed subscribes lazily; missing daily data is a visible warmup state.
    snapshot=feed.snapshot(symbol)
    def serialize(rows):
        return [{'timestamp':r['timestamp'],'open':r['open'],'high':r['high'],'low':r['low'],
                 'close':r['price'],'volume':r.get('volume',0),'openInterest':r.get('openInterest',0),
                 'contract':contract}
                for r in rows if all(key in r for key in ['timestamp','open','high','low','price'])
                and completed_daily_bar(datetime.fromisoformat(r['timestamp']),now)]
    return {'symbol':symbol,'contract':contract,'marketState':context['marketState'],
        'checkedAt':context['checkedAt'],'source':quote.get('source','天勤真实行情'),
        'quote':{'symbol':contract,'price':quote['price'],'dataTimestamp':quote['dataTimestamp'],
                 'dataStatus':quote.get('dataStatus','CACHED'),'source':quote.get('source','天勤真实行情')},
        'spec':{'contract':contract,**{key:quote[key] for key in required}},
        'signalBars':serialize(snapshot.get('history',[])),'executionBars':serialize(context.get('history',[]))}
