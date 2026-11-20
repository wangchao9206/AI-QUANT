"""Bounded, stateless paper-strategy API inputs and market-context adapters."""
from datetime import date, datetime, time, timedelta
from typing import Literal
import math
import re

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from algorithm_service.personal_trinity import TrinityRules
from backtesting.personal_ma_execution import TRIGGER_SIDES
from backtesting.personal_ma_multiframe_signals import _session_bounds, _session_offsets, minute_events
from backtesting.personal_ma_signals import ma_tape
from config.settings import settings
from data.data_feed import KLineBar
from data.trading_day import completed_daily_bar
from data.live_feed import SHANGHAI, root_symbol
from backtesting.strategy_signals import STRATEGY_NAMES, daily_signal, daily_atr

StrategyId = Literal['MA20_MACD','HOLISTIC_14D','MOMENTUM_BREAKOUT','BOLLINGER_REVERSAL','DUAL_THRUST','ADAPTIVE_CTA','BUY_AND_HOLD','WORKFLOW','PERSONAL_TRINITY']
STRATEGY_VERSION = 'paper-daily-v1'
TRINITY_CONTRACT = r'^(FG|SA|AP|CJ)[0-9]{3,4}$'
TRINITY_MINUTE_WARMUP = 24
TRINITY_DECISION_TTL = timedelta(minutes=2)


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


class PaperTrinityRules(TrinityRules):
    symbol: str | None = Field(default=None, pattern=TRINITY_CONTRACT)
    costMultiplier: Literal[1, 2] | None = None

    @field_validator('costMultiplier', mode='before')
    @classmethod
    def integer_cost(cls, value):
        return None if value is None else cls.integer_option(value)


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
    minute_bars: list[SignalBar] = Field(default_factory=list, alias='minuteBars', max_length=2000)
    price_tick: float = Field(default=1, alias='priceTick', gt=0, allow_inf_nan=False)
    trinity: PaperTrinityRules | None = None
    minute_cadence: Literal[1, 5, 15] = Field(default=1, alias='minuteCadence')
    minute_trading_dates: list[date] = Field(default_factory=list, alias='minuteTradingDates', max_length=2000)
    trading_sessions: dict[Literal['day', 'night'], list[tuple[str, str]]] = Field(default_factory=dict, alias='tradingSessions')
    trading_date: date | None = Field(default=None, alias='tradingDate')
    last_signal_time: datetime | None = Field(default=None, alias='lastSignalTime')
    last_entry_signal_time: datetime | None = Field(default=None, alias='lastEntrySignalTime')
    position_opened_at: datetime | None = Field(default=None, alias='positionOpenedAt')
    started_at: datetime | None = Field(default=None, alias='startedAt')
    position_lots: int = Field(default=0, alias='positionLots', ge=0, le=1000000)

    @field_validator('as_of', 'last_signal_time', 'last_entry_signal_time', 'position_opened_at', 'started_at')
    @classmethod
    def aware(cls, value):
        if value is not None and value.utcoffset() is None:
            raise ValueError('决策时点必须包含时区')
        return value

    @model_validator(mode='after')
    def valid_trinity_input(self):
        if self.strategy != 'PERSONAL_TRINITY':
            if self.trinity is not None or len(self.minute_bars) > 600:
                raise ValueError('当前策略不能使用三位一体配置或超长分钟序列')
            return self
        if (self.trinity is None or self.workflow is not None
                or not re.fullmatch(TRINITY_CONTRACT, self.symbol)
                or self.trinity.symbol not in (None, self.symbol)):
            raise ValueError('请提供三位一体配置和对应的实际交割合约')
        if len(self.minute_bars) != len(self.minute_trading_dates):
            raise ValueError('分钟线必须逐根提供交易所交易日')
        if bool(self.direction) != bool(self.position_lots):
            raise ValueError('持仓方向和手数不一致')
        times = (self.last_signal_time, self.last_entry_signal_time, self.position_opened_at, self.started_at)
        if any(stamp is not None and stamp > self.as_of for stamp in times):
            raise ValueError('策略状态不能晚于本次决策时点')
        return self


def evaluate(request: StrategyRequest):
    if request.strategy == 'PERSONAL_TRINITY':
        return evaluate_trinity(request)
    if request.strategy == 'MA20_MACD':
        return evaluate_ma20_macd(request)
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
        'modelVersion':('workflow-daily-v2' if request.workflow and request.workflow.get('schemaVersion')==2 else 'workflow-daily-v1') if request.strategy=='WORKFLOW' else STRATEGY_VERSION,'signal':result.signal,'reason':result.reason,
        'signalTime':bars[-1].timestamp if bars else None,'historyCount':len(bars),
        'requiredBars':result.required_bars,'atr':daily_atr(execution,contract_aware=True) if execution else 0,
        'signalBasis':'OBSERVED_CONTINUOUS_DAILY','riskBasis':'OBSERVED_DELIVERY_DAILY',
        'nodeTrace':result.node_trace or []}


def evaluate_ma20_macd(request: StrategyRequest):
    if request.workflow is not None:
        raise HTTPException(422, '分钟策略不能携带工作流')
    def ordered(rows):
        if any(a.timestamp >= b.timestamp for a, b in zip(rows, rows[1:])):
            raise HTTPException(422, '行情必须严格按时间排序')
        for row in rows:
            row.bar()
            if row.contract != request.symbol:
                raise HTTPException(422, '行情必须属于同一实际合约')
        return rows
    daily = ordered([b for b in request.bars if completed_daily_bar(b.timestamp, request.as_of)])
    minutes = ordered([b for b in request.minute_bars if b.timestamp + timedelta(seconds=60) <= request.as_of])
    signal, reason = 'WARMING', '等待35根已完成日线和21根已完成分钟线'
    trace = []
    if len(minutes) >= 21 and (len(daily) >= 35 or request.direction != 0):
        fast = slow = daily[0].close if daily else 0.0
        dea = 0.0
        for bar in daily[1:]:
            fast += (bar.close-fast)*2/13
            slow += (bar.close-slow)*2/27
            dea += ((fast-slow)-dea)*2/10
        dif = fast-slow
        prev_ma = sum(b.close for b in minutes[-21:-1])/20
        ma = sum(b.close for b in minutes[-20:])/20
        previous, last = minutes[-2].close, minutes[-1].close
        signal, reason = ma20_macd_action(previous, last, prev_ma, ma, dif, dea,
                                         request.direction, request.price_tick)
        trace = [{'nodeId': 'ma20-macd', 'label': '已完成行情指标', 'type': 'INDICATORS',
                  'status': signal, 'value': {'ma20': ma, 'previousMa20': prev_ma,
                  'dif': dif, 'dea': dea, 'dailyTime': daily[-1].timestamp.isoformat() if daily else None}, 'reason': reason}]
    return {'strategy': 'MA20_MACD', 'strategyName': '分钟MA20＋日线MACD',
            'modelVersion': 'paper-ma20-macd-v1', 'signal': signal, 'reason': reason,
            'signalTime': minutes[-1].timestamp if minutes else None, 'historyCount': len(minutes),
            'requiredBars': 21, 'atr': 0, 'nodeTrace': trace}


def ma20_macd_action(previous, last, previous_mean, mean, dif, dea, direction, price_tick):
    if direction > 0 and last <= mean - 3 * price_tick:
        return 'FLATTEN', '分钟收盘跌破MA20至少3跳，平多后等待新突破'
    if direction < 0 and last >= mean + 3 * price_tick:
        return 'FLATTEN', '分钟收盘突破MA20至少3跳，平空后等待新突破'
    if direction == 0:
        if previous <= previous_mean and last > mean and dif > dea:
            return 'BUY', '日线MACD多头，已完成分钟线向上突破MA20'
        if previous >= previous_mean and last < mean and dif < dea:
            return 'SELL', '日线MACD空头，已完成分钟线向下跌破MA20'
    return 'HOLD', '等待新的MA20突破；日线MACD过滤方向'


def _trinity_daily(request: StrategyRequest):
    rows = request.execution_bars or request.bars
    completed = []
    days = []
    for row in rows:
        day = row.timestamp.astimezone(SHANGHAI).date()
        close_at = datetime.combine(day, time(15), SHANGHAI)
        if close_at <= request.as_of and row.timestamp <= request.as_of:
            if row.contract != request.symbol or (days and day <= days[-1]):
                raise HTTPException(422, '日线必须按交易日递增并属于同一实际合约')
            completed.append(row.bar())
            days.append(day)
    return completed, days


def _recent_trinity_confirmation(stamp, as_of, sessions):
    if as_of - stamp <= TRINITY_DECISION_TTL:
        return True
    # A bucket ending at an exchange break can only trade at reopening.
    offsets = _session_offsets(sessions)
    try:
        _, _, previous_close = _session_bounds(stamp - timedelta(microseconds=1), offsets)
        _, current_open, _ = _session_bounds(as_of, offsets)
    except ValueError:
        return False
    return stamp == previous_close and stamp < current_open and as_of - current_open <= TRINITY_DECISION_TTL


def evaluate_trinity(request: StrategyRequest):
    """Evaluate fresh completed confirmations against actual filled position state."""
    rules = request.trinity
    assert rules is not None
    daily, days = _trinity_daily(request)
    required_daily = rules.slowPeriod + 1
    atr = daily_atr(daily, contract_aware=True)
    evidence = {}
    buckets_count = 0

    def decision(signal, reason, stamp=None):
        return {
            'strategy': 'PERSONAL_TRINITY', 'strategyName': '自研道氏-威科夫-缠论三位一体',
            'modelVersion': 'paper-personal-trinity-v1', 'signal': signal, 'reason': reason,
            'signalTime': stamp, 'historyCount': buckets_count, 'requiredBars': TRINITY_MINUTE_WARMUP,
            'atr': atr, 'signalBasis': 'OBSERVED_DELIVERY_DAILY_AND_COMPLETED_MINUTES',
            'riskBasis': 'OBSERVED_DELIVERY_DAILY',
            'nodeTrace': [{'nodeId': 'personal-trinity', 'label': '日线方向与分钟确认',
                           'type': 'INDICATORS', 'status': signal,
                           'reason': reason, 'value': {**evidence, 'dailyBars': len(daily),
                                                       'requiredDailyBars': required_daily}}],
        }

    if len(daily) < required_daily:
        return decision('WARMING', f'等待至少{required_daily}根已完成日线')
    tape = ma_tape(daily, periods=(rules.fastPeriod, rules.mediumPeriod, rules.slowPeriod),
                   convergence_days=rules.convergenceDays)
    evidence.update({key: tape[-1][key] for key in ('ma5', 'ma10', 'ma20', 'trend')})
    setup = next(((day, item['trigger']) for day, item in reversed(list(zip(days, tape)))
                  if item['trigger']), None)
    if setup is not None:
        setup_day, trigger = setup
        known_at = datetime.combine(setup_day, time(15), SHANGHAI)
        side = TRIGGER_SIDES[trigger]
        evidence.update(dailyKnownAt=known_at.isoformat(), dailyTrigger=trigger)
        if (request.direction == -side
                and (request.position_opened_at is None or known_at >= request.position_opened_at)
                and (request.last_signal_time is None or known_at > request.last_signal_time)):
            return decision('FLATTEN', '日线方向反手，先平原有反向持仓', known_at)

    if request.trading_date is None or not request.trading_sessions or not request.minute_bars:
        return decision('WARMING', '等待已核验的分钟行情、交易日和交易时段')
    if days[-1] > request.trading_date:
        raise HTTPException(422, '日线交易日不能晚于当前交易日')
    cadence = timedelta(minutes=request.minute_cadence)
    paired = [(row.bar(), day) for row, day in zip(request.minute_bars, request.minute_trading_dates)
              if row.timestamp + cadence <= request.as_of]
    if not paired:
        return decision('WARMING', '等待已完成的分钟行情')
    minutes, minute_days = zip(*paired)
    if any(row.contract_symbol != request.symbol for row in minutes) or minute_days[-1] > request.trading_date:
        raise HTTPException(422, '分钟行情合约或交易日不匹配')
    try:
        scanned = minute_events(minutes, minute_days, request.trading_sessions, request.minute_cadence,
                                periods=(rules.entryMinutes,))[rules.entryMinutes]
    except ValueError as exc:
        raise HTTPException(422, '分钟线顺序或交易时段无效') from exc
    buckets = scanned['buckets']
    buckets_count = len(buckets)
    if buckets_count < TRINITY_MINUTE_WARMUP:
        return decision('WARMING', f'等待至少{TRINITY_MINUTE_WARMUP}根已完成{rules.entryMinutes}分钟线')

    stamp = buckets[-1].timestamp
    if (scanned['scoringDaysByTime'][stamp] != request.trading_date
            or not _recent_trinity_confirmation(stamp, request.as_of, request.trading_sessions)):
        return decision('HOLD', '等待本交易日新的分钟收线')
    if request.started_at is None:
        return decision('WARMING', '等待策略启动时点校验')
    if stamp <= max(request.started_at, request.last_signal_time or request.started_at):
        return decision('HOLD', '等待启动或上一次委托信号之后的新确认')

    sides = scanned[rules.confirmation].get(stamp, ())
    if isinstance(sides, int):
        sides = (sides,)
    evidence.update(confirmationAt=stamp.isoformat(), confirmationMode=rules.confirmation,
                    chanDirection=scanned['chan'].get(stamp),
                    wyckoffDirection=scanned['wyckoff'].get(stamp))
    trend = tape[-1]['trend']
    if trend not in sides:
        return decision('HOLD', '当前分钟未出现符合日线方向的新确认')

    if setup is not None:
        dates = set(days).union(minute_days, (request.trading_date,))
        age = sum(setup_day < day <= request.trading_date for day in dates)
        active = stamp >= known_at and trend == side and age <= rules.waitTradingDays
        if (active and request.direction == 0
                and (request.last_entry_signal_time is None or request.last_entry_signal_time < known_at)):
            signal = 'BUY' if side > 0 else 'SELL'
            return decision(signal, '日线方向与已完成分钟确认同向，按首仓手数开仓', stamp)
        new_position_confirmation = request.position_opened_at is not None and stamp > request.position_opened_at
        if (request.direction == trend == 1 and request.position_lots == 1
                and new_position_confirmation and rules.addMode != 'NONE'):
            if active and trigger == 'LONG_REENTRY' and known_at > request.position_opened_at:
                return decision('ADD_LONG', '日线均线收敛后重新向上穿越，分钟确认加多', stamp)
            if rules.addMode == 'MINUTE_ADD':
                return decision('ADD_LONG', '首仓成交后出现新的同向分钟确认，加多', stamp)
    return decision('HOLD', '等待有效的日线触发或加仓条件')


def live_context(feed, symbol: str, include_history: bool = True):
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
    snapshot=feed.snapshot(symbol) if include_history else {}
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
        'signalBars':serialize(snapshot.get('history',[])),
        'executionBars':serialize(context.get('history',[])) if include_history else []}


class PortfolioQuotesRequest(BaseModel):
    contracts: list[str] = Field(min_length=1, max_length=100)


class StartupRefreshRequest(BaseModel):
    requestKey: str = Field(pattern=r'^[A-Za-z0-9:._-]{8,128}$')


def portfolio_quotes(feed, contracts: list[str]):
    import re
    if any(not re.fullmatch(r'[A-Z]{1,4}[0-9]{3,4}', contract) for contract in contracts):
        raise HTTPException(422, '批量行情必须使用实际合约')
    quotes, errors = {}, {}
    for contract in dict.fromkeys(contracts):
        try:
            context = live_context(feed, contract, include_history=False)
            if context['contract'] != contract:
                raise HTTPException(503, '行情合约不匹配')
            quotes[contract] = context
        except Exception:
            errors[contract] = '该合约真实行情或规格暂不可用'
    return {'quotes': quotes, 'errors': errors}
