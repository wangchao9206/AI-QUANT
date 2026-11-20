"""Historical replay of the paper MA20/MACD signal on the verified FG701 archive."""

from bisect import bisect_right
from collections import defaultdict, deque
from datetime import date, datetime, time, timedelta
from math import isfinite, isclose
from threading import BoundedSemaphore
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from algorithm_service.paper_strategy import ma20_macd_action
from backtesting.backtester import FuturesExecutionLedger
from backtesting.personal_ma_execution import INITIAL_CASH
from data.intraday_replay import SH, load
from data.tqsdk_backtest import FuturesContractSpec


class Ma20BacktestRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    symbol: Literal['FG701']
    startDate: date | None = None
    endDate: date | None = None
    costMultiplier: Literal[1, 2] = 1

    @field_validator('costMultiplier', mode='before')
    @classmethod
    def integer_cost(cls, value):
        if type(value) is not int:
            raise ValueError('请选择整数成本倍数')
        return value

    @model_validator(mode='after')
    def ordered_dates(self):
        if self.startDate is not None and self.endDate is not None and self.startDate > self.endDate:
            raise ValueError('结束日期不能早于开始日期')
        return self


MINUTE = timedelta(minutes=1)
DAY_END = time(14, 59)
SESSION_WINDOWS = ((21 * 60, 23 * 60), (9 * 60, 10 * 60 + 15),
                   (10 * 60 + 30, 11 * 60 + 30), (13 * 60 + 30, 15 * 60))
EXPECTED_MINUTES = {minute for start, end in SESSION_WINDOWS for minute in range(start, end)}


def _prepared_rows(archive, first, last):
    by_day = defaultdict(list)
    minute_rows = []
    for row in archive['bars']:
        stamp = datetime.fromisoformat(row['timestamp']).astimezone(SH)
        day = date.fromisoformat(row['tradingDate'])
        if row.get('contract') != archive['symbol'] or stamp.second or stamp.microsecond:
            raise ValueError('分钟合约或时间不符')
        if minute_rows and day < minute_rows[-1][2]:
            raise ValueError('交易日序列无序')
        minute_rows.append((row, stamp, day))
        if first <= day <= last:
            by_day[day].append((stamp, row['volume']))

    macd = []
    stamps = []
    dates = []
    for row in archive['dailyMacd']:
        stamp = datetime.fromisoformat(row['availableAt'])
        day = date.fromisoformat(row['date'])
        if (stamp.utcoffset() is None or stamp.astimezone(SH).date() != day
                or stamp.astimezone(SH).time() < time(15)
                or dates and day <= dates[-1]
                or not isfinite(row['dif']) or not isfinite(row['dea'])):
            raise ValueError('日线MACD时间或数值无效')
        dates.append(day)
        stamps.append(stamp)
        macd.append((row['dif'], row['dea']) if row['ready'] is True else None)

    expected_days = {day for day in dates if first <= day <= last}
    if not expected_days:
        raise HTTPException(422, detail='所选日期没有完整交易日')
    if set(by_day) != expected_days:
        raise ValueError('评分窗口缺少日线或分钟交易日')
    for rows in by_day.values():
        clocks = [stamp.hour * 60 + stamp.minute for stamp, _ in rows]
        if (len(clocks) != len(EXPECTED_MINUTES) or set(clocks) != EXPECTED_MINUTES
                or rows[-1][0].time() != DAY_END or rows[-1][1] <= 0):
            raise ValueError('评分窗口存在不完整交易时段')
    return minute_rows, macd, stamps, expected_days


def backtest(request: Ma20BacktestRequest):
    try:
        archive = load(request.symbol)
        first = request.startDate or date.fromisoformat(archive['startDate'])
        last = request.endDate or date.fromisoformat(archive['endDate'])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(503, detail='分钟MA20＋日线MACD的已核验行情档案尚未就绪') from exc
    if not date.fromisoformat(archive['startDate']) <= first <= last <= date.fromisoformat(archive['endDate']):
        raise HTTPException(422, detail='所选日期必须在 2026-10-19 至 2026-11-16 的核验区间内')

    try:
        rows, macd, macd_stamps, days = _prepared_rows(archive, first, last)
        raw = archive['spec']
        spec = FuturesContractSpec(request.symbol, raw['volumeMultiple'], raw['priceTick'],
                                   raw['marginPerLot'], raw['commissionPerLot'] * request.costMultiplier)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(503, detail='分钟或日线MACD档案未通过完整性检查') from exc

    ledger = FuturesExecutionLedger(INITIAL_CASH)
    close_window = deque(maxlen=21)
    trades = []
    costs = {'slippage_ticks': request.costMultiplier, 'fee_rate': 0}
    pending = entry = previous_day = None
    peak = INITIAL_CASH
    fees = slippage = drawdown = 0.0

    def close(price, stamp, reason):
        nonlocal entry, fees, slippage
        fill = ledger.close_position(market_price=price, spec=spec, **costs)
        fees += fill.fee
        slippage += fill.slippage_cost
        trades.append({**entry, 'exitAt': stamp.isoformat(), 'exitPrice': fill.price,
                       'exitReason': reason, 'netPnl': fill.trade_net_pnl})
        entry = None

    for row, stamp, day in rows:
        if day > last:
            break
        close_window.append(row['close'])
        if day < first:
            continue
        if previous_day != day:
            pending = None
            previous_day = day
        executed_close = False
        if stamp.time() == DAY_END:
            if ledger.direction:
                close(row['open'], stamp, 'DAY_END')
            pending = None
        elif row['volume'] > 0:
            stop = ledger.entry_price - ledger.direction * 10 * spec.price_tick
            if ledger.direction and ledger.direction * (row['open'] - stop) <= 0:
                close(row['open'], stamp, 'STOP_GAP')
                executed_close = True
            elif pending:
                action, signal_at = pending
                if action == 'FLATTEN' and ledger.direction:
                    close(row['open'], stamp, 'MEAN_REVERSAL')
                    executed_close = True
                elif action in ('BUY', 'SELL') and not ledger.direction:
                    side = 1 if action == 'BUY' else -1
                    fill = ledger.open_position(
                        direction=side, contract=spec.contract, market_price=row['open'], spec=spec,
                        margin_rate=.12, margin_budget_ratio=.20, target_leverage=2, fixed_lots=1, **costs,
                    )
                    if fill.lots:
                        entry = {'direction': side, 'signalAt': signal_at.isoformat(),
                                 'entryAt': stamp.isoformat(), 'entryPrice': fill.price}
                        fees += fill.fee
                        slippage += fill.slippage_cost
                pending = None
            if ledger.direction:
                stop = ledger.entry_price - ledger.direction * 10 * spec.price_tick
                if (ledger.direction > 0 and row['low'] <= stop
                        or ledger.direction < 0 and row['high'] >= stop):
                    # Minute OHLC proves the threshold was reached. It cannot locate the fill within the minute.
                    close(stop, stamp + MINUTE, 'STOP')
                    executed_close = True
            if not executed_close and len(close_window) == 21:
                signal_at = stamp + MINUTE
                idx = bisect_right(macd_stamps, signal_at) - 1
                daily = macd[idx] if idx >= 0 else None
                closes = list(close_window)
                if daily is not None or ledger.direction:
                    action, _ = ma20_macd_action(
                        closes[-2], closes[-1], sum(closes[:-1]) / 20, sum(closes[1:]) / 20,
                        *(daily or (0, 0)), ledger.direction, spec.price_tick,
                    )
                    pending = None if action == 'HOLD' else (action, signal_at)
        equity = ledger.equity(row['close'], spec)
        peak = max(peak, equity)
        drawdown = max(drawdown, (peak - equity) / peak)

    pnl = ledger.cash - INITIAL_CASH
    if ledger.direction or not isclose(sum(trade['netPnl'] for trade in trades), pnl, abs_tol=1e-6):
        raise RuntimeError('分钟MA20回测账本未完成对账')
    return {
        'symbol': request.symbol,
        'scope': {'first': min(days).isoformat(), 'last': max(days).isoformat(), 'scoreDays': len(days)},
        'sourceSha256': archive['sourceSha256'],
        'metrics': {'initialCash': INITIAL_CASH, 'netPnl': pnl, 'returnPct': pnl / INITIAL_CASH * 100,
                    'maxDrawdownPct': drawdown * 100, 'primaryOpens': len(trades), 'closedTrades': len(trades),
                    'fees': fees, 'slippageCost': slippage},
        'trades': trades,
    }


def router_for(capacity: BoundedSemaphore):
    router = APIRouter(prefix='/api/v1/research/ma20-macd', tags=['Minute MA20 and Daily MACD'])

    @router.post('/backtest')
    def run(request: Ma20BacktestRequest):
        if not capacity.acquire(blocking=False):
            raise HTTPException(429, detail='历史回测正在运行，请稍后重试')
        try:
            return backtest(request)
        finally:
            capacity.release()

    return router
