"""Verified 15-minute historical replay of the MA workflow, without paper-account writes."""

from collections import Counter
from dataclasses import dataclass, replace
from datetime import date, datetime
from hashlib import sha256
import json
import logging
from math import floor
import os
from pathlib import Path
from threading import BoundedSemaphore
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from algorithm_service.ma_trend_workflow import BAR_SIZE, SIDES, _daily_indicators, _minute_indicators
from algorithm_service.personal_trinity import ARCHIVE_NAME
from backtesting.backtester import FuturesExecutionLedger
from data.tqsdk_backtest import FuturesContractSpec
from scripts.research_personal_ma_multiframe import HISTORY, MULTI_WINDOW, validated_sdk_inputs


logger = logging.getLogger(__name__)
MAX_REVIEW_BARS = 4096
ASSUMPTIONS = [
    '在实际交割合约上回放。日线触发只在下一交易日等待首根已完成的同向 15 分钟 K 线。MACD、DKX 不参与筛选。',
    '确认后在下一根有交易的 K 线按开盘价加不利滑点撮合。反手先平，平完后再等下一根开仓。',
    '开仓和加仓使用可用资金的一半估算手数，保证金取档案金额和 12% 名义保证金中的较高值。撮合量最多为前一根成交量的 10%，也不超过成交 K 线实际总量。',
    '以持仓均价为基准，收盘达到目标价格幅度后申请平掉当时手数的一半，向下取整。每次开仓或加仓后最多触发一次。',
    '期末未平仓按最后一根收盘价计入浮动盈亏，不强制平仓。',
]


class ReplayRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    symbol: Literal['FG701', 'SA701', 'AP701', 'CJ701']
    initialCash: float = Field(ge=1_000, le=100_000_000, allow_inf_nan=False)
    takeProfitPct: float = Field(ge=.01, le=50, allow_inf_nan=False)
    costMultiplier: Literal[1, 2] = 1
    includeTimeline: bool = False

    @field_validator('costMultiplier', mode='before')
    @classmethod
    def integer_cost(cls, value):
        if type(value) is not int:
            raise ValueError('请选择整数成本倍数')
        return value


@dataclass
class Order:
    action: str
    side: int
    signal_at: datetime
    remaining: int = 0


class Ledger:
    def __init__(self, initial_cash: float, spec: FuturesContractSpec, cost_multiplier: int):
        self.cash = initial_cash
        self.spec = replace(spec, commission_per_lot=spec.commission_per_lot * cost_multiplier)
        self.slippage_ticks = cost_multiplier
        self.fee_rate = .0001 * cost_multiplier
        self.side = self.lots = 0
        self.average = self.realized = self.fees = self.slippage = 0.0
        self.executions = []

    def marked_pnl(self, price):
        return self.side * (price - self.average) * self.lots * self.spec.volume_multiple

    def _margin(self, price):
        return FuturesExecutionLedger._margin_per_lot(price, self.spec, .12)

    def _fee(self, price, lots):
        return FuturesExecutionLedger._fee(price, lots, self.spec, self.fee_rate)

    def _price(self, bar, side):
        return FuturesExecutionLedger._fill_price(bar.open, side, self.spec, self.slippage_ticks)

    def enter(self, bar, order: Order, capacity: int):
        if self.side not in (0, order.side):
            raise ValueError('Cannot add to an opposite position')
        price = self._price(bar, order.side)
        free_cash = self.cash + self.marked_pnl(bar.open) - self.lots * self._margin(bar.open)
        per_lot = self._margin(max(bar.open, price)) + self._fee(price, 1)
        per_lot += abs(price - bar.open) * self.spec.volume_multiple
        lots = min(capacity, max(0, floor(free_cash / (2 * per_lot))))
        if lots:
            self.average = (self.average * self.lots + price * lots) / (self.lots + lots)
            self.lots += lots
            self.side = order.side
            self._record(bar, order, price, lots, 0.0)
        return lots

    def close(self, bar, order: Order, capacity: int):
        if self.side == 0 or self.side != order.side:
            raise ValueError('Nothing to close on the requested side')
        lots = min(capacity, order.remaining, self.lots)
        price = self._price(bar, -self.side)
        realized = self.side * (price - self.average) * lots * self.spec.volume_multiple
        self.lots -= lots
        if self.lots == 0:
            self.side = self.average = 0
        self._record(bar, order, price, lots, realized)
        return lots

    def _record(self, bar, order, price, lots, realized):
        fee = self._fee(price, lots)
        slippage = abs(price - bar.open) * lots * self.spec.volume_multiple
        self.cash += realized - fee
        self.realized += realized
        self.fees += fee
        self.slippage += slippage
        self.executions.append({'at': bar.timestamp, 'signalAt': order.signal_at, 'action': order.action,
                                'direction': order.side, 'lots': lots, 'price': price, 'fee': round(fee, 2)})


def _review_frame(bar, trading_day, indicators, ledger, equity, daily_day, daily_setup,
                  signal, reason, pending, first_fill):
    return {
        'at': bar.timestamp + BAR_SIZE,
        'openAt': bar.timestamp,
        'tradingDate': trading_day,
        'open': bar.open, 'high': bar.high, 'low': bar.low, 'close': bar.close, 'volume': bar.volume,
        'equity': round(equity, 2), 'direction': ledger.side, 'lots': ledger.lots,
        'averagePrice': round(ledger.average, 6) if ledger.lots else None,
        'dailyTrigger': daily_setup, 'dailySignalDate': daily_day,
        'minuteTrend': indicators['trend'], 'minuteMa20': indicators.get('ma20'),
        'minuteDif': indicators.get('dif'), 'minuteDea': indicators.get('dea'),
        'minuteMacdCross': indicators.get('macdCross'),
        'minuteDkx': indicators.get('dkx'), 'minuteMadkx': indicators.get('madkx'),
        'signal': signal, 'signalReason': reason, 'pendingAction': pending.action if pending else None,
        'executionIndexes': list(range(first_fill, len(ledger.executions))),
    }


def run_replay(request: ReplayRequest, minutes, trading_days, daily, spec, first: date, last: date):
    if (len(minutes) != len(trading_days) or not minutes
            or any(left.timestamp >= right.timestamp for left, right in zip(minutes, minutes[1:]))
            or any(left > right for left, right in zip(trading_days, trading_days[1:]))
            or any(bar.contract_symbol != spec.contract for bar in minutes)):
        raise ValueError('Unordered or mismatched actual-contract replay bars')
    ledger = Ledger(request.initialCash, spec, request.costMultiplier)
    daily_signals = dict(_daily_indicators(daily))
    ordered_days = list(dict.fromkeys(trading_days))
    previous_days = dict(zip(ordered_days[1:], ordered_days[:-1]))
    counts = Counter()
    pending = None
    day = None
    daily_day = daily_setup = None
    consumed_profit = False
    previous_volume = 0
    peak = request.initialCash
    drawdown = 0.0
    final_price = None
    scores = set()
    timeline = [] if request.includeTimeline else None
    for bar, stamp_day, indicators in zip(minutes, trading_days, _minute_indicators(minutes), strict=True):
        # The preceding bar controls the model capacity. Recorded total volume can only further reduce fills.
        capacity = min(previous_volume // 10, bar.volume)
        previous_volume = bar.volume
        if not first <= stamp_day <= last:
            continue
        scores.add(stamp_day)
        if day != stamp_day:
            day = stamp_day
            daily_day = previous_days.get(day)
            daily_setup = candidate = daily_signals.get(daily_day, {}).get('trigger')
        first_fill = len(ledger.executions)
        signal = 'HOLD'
        reason = '没有新的日线候选或止盈信号'
        if pending is not None and capacity > 0 and bar.timestamp >= pending.signal_at:
            if pending.action in ('OPEN', 'ADD'):
                if ledger.enter(bar, pending, capacity):
                    counts[pending.action] += 1
                    consumed_profit = False
                else:
                    reason = '按可用资金的一半计算，未达到一手，开仓或加仓未成交'
                pending = None
            else:
                remaining = pending.remaining - ledger.close(bar, pending, capacity)
                pending.remaining = remaining
                if not remaining:
                    counts[pending.action] += 1
                    pending = (Order('OPEN', -pending.side, pending.signal_at)
                               if pending.action == 'REVERSAL_CLOSE' else None)

        at = bar.timestamp + BAR_SIZE
        side = SIDES.get(candidate, 0)
        if side and indicators['trend'] == side:
            # Consume each daily setup on its first qualifying minute, even if it is not actionable.
            trigger, candidate = candidate, None
            if ledger.side == -side:
                pending = Order('REVERSAL_CLOSE', ledger.side, at, ledger.lots)
                signal, reason = 'REVERSAL_CLOSE', '15 分钟同向确认，先平反向持仓，随后等下一根可成交行情开反向仓'
            elif ledger.side == 0:
                pending = Order('OPEN', side, at)
                signal, reason = 'OPEN', '15 分钟同向确认，等下一根可成交行情按可用资金的一半开仓'
            elif trigger == 'LONG_REENTRY' and side == 1 and pending is None:
                pending = Order('ADD', side, at)
                signal, reason = 'ADD', '多头收敛后的同向确认，等下一根可成交行情按可用资金的一半加仓'
            else:
                reason = '15 分钟已同向确认，当前同方向持仓或已有委托，本候选不再开仓'
        elif side:
            reason = '等待本交易日 15 分钟收盘与日线候选同向'

        if pending is None and not consumed_profit and ledger.lots >= 2:
            movement = ledger.side * (bar.close - ledger.average) / ledger.average * 100
            if movement >= request.takeProfitPct:
                pending = Order('TAKE_PROFIT', ledger.side, at, ledger.lots // 2)
                consumed_profit = True
                signal, reason = 'TAKE_PROFIT', '15 分钟收盘达到盈利目标，等下一根可成交行情平持仓的一半'

        final_price = bar.close
        equity = ledger.cash + ledger.marked_pnl(final_price)
        peak = max(peak, equity)
        drawdown = max(drawdown, (peak - equity) / peak)
        if timeline is not None:
            if len(timeline) >= MAX_REVIEW_BARS:
                raise ValueError('Review timeline exceeds maximum number of historical bars')
            if signal == 'HOLD' and pending is not None:
                signal, reason = 'WAIT', '已有待撮合委托，等待下一根有可成交量的行情'
            timeline.append(_review_frame(bar, stamp_day, indicators, ledger, equity, daily_day, daily_setup,
                                          signal, reason, pending, first_fill))

    if final_price is None:
        raise ValueError('No verified replay bars in the scoring window')
    unrealized = ledger.marked_pnl(final_price)
    ending_equity = ledger.cash + unrealized
    net = ending_equity - request.initialCash
    result = {
        'symbol': request.symbol,
        'scope': {'first': min(scores), 'last': max(scores), 'scoreDays': len(scores)},
        'configuration': request.model_dump(exclude={'includeTimeline'}),
        'metrics': {'initialCash': request.initialCash, 'endingEquity': round(ending_equity, 2),
                    'netPnl': round(net, 2), 'returnPct': round(net / request.initialCash * 100, 4),
                    'maxDrawdownPct': round(drawdown * 100, 4), 'entryCount': counts['OPEN'],
                    'addCount': counts['ADD'], 'takeProfitCount': counts['TAKE_PROFIT'],
                    'reversalCount': counts['REVERSAL_CLOSE'], 'fees': round(ledger.fees, 2),
                    'slippageCost': round(ledger.slippage, 2), 'realizedPnl': round(ledger.realized, 2),
                    'unrealizedPnl': round(unrealized, 2), 'openLots': ledger.lots},
        'executions': ledger.executions,
        'position': {'direction': ledger.side, 'lots': ledger.lots, 'averagePrice': round(ledger.average, 6)},
        'assumptions': ASSUMPTIONS,
    }
    if timeline is not None:
        result['reviewTimeline'] = timeline
    return result


def replay(request: ReplayRequest, history: Path):
    try:
        raw = (history / ARCHIVE_NAME).read_bytes()
        archive = json.loads(raw)
        minutes, days, _, daily, spec, _ = validated_sdk_inputs(archive, request.symbol, MULTI_WINDOW, history=history)
        result = run_replay(request, minutes, days, daily, spec, *MULTI_WINDOW)
        result['reviewDatasetId'] = sha256(raw).hexdigest()
        return result
    except (OSError, ValueError, KeyError, TypeError, OverflowError) as exc:
        logger.warning('Could not replay MA workflow archive for %s', request.symbol, exc_info=True)
        raise HTTPException(503, detail='暂时无法回放已核验的日线与 15 分钟行情') from exc


def router_for(capacity: BoundedSemaphore):
    router = APIRouter(prefix='/internal/v1/workflows')

    @router.post('/ma-trend-replay')
    def run(request: ReplayRequest):
        if not capacity.acquire(blocking=False):
            raise HTTPException(429, detail='历史模拟正在运行，请稍后重试')
        try:
            return replay(request, Path(os.environ.get('HISTORY_CACHE_DIR', str(HISTORY))))
        finally:
            capacity.release()

    return router
