# -*- coding: utf-8 -*-
"""
AI-QUANT 多维量化回测与模拟交易引擎 (Quantitative Backtester)
支持真实量价多维信号、动量突破、布林带自适应均值回归、Dual Thrust 及全天候 CTA 趋势策略
真实模拟中国商品与股指期货市场交易实务：包含真实保证金有效杠杆、万分之一手续费与滑点跳数、
ATR 跟踪止盈止损与吊灯锁盈 (Chandelier Exit)、资金曲线复利计算与机构级绩效评价指标。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from data.data_feed import KLineBar, MarketQuote
from data.tqsdk_backtest import FuturesContractSpec, RollEvent
from engines.fusion_engine import HolisticFusionEngine


@dataclass
class TradeRecord:
    timestamp: datetime
    action: str        # OPEN_BUY, OPEN_SHORT, FLATTEN_LONG, FLATTEN_SHORT, FINAL_FLATTEN
    price: float
    position_pct: float
    pnl: float = 0.0
    return_pct: float = 0.0
    reason: str = ""
    hold_bars: int = 0
    contract: str | None = None
    lots: int = 0
    fee: float = 0.0
    slippage_cost: float = 0.0
    from_contract: str | None = None
    to_contract: str | None = None
    old_price: float | None = None
    new_price: float | None = None
    price_gap: float | None = None


@dataclass
class DailyEquityPoint:
    date: str
    equity: float
    benchmark_equity: float
    cash: float
    position_pct: float
    daily_return_pct: float
    drawdown_pct: float


@dataclass
class BacktestResult:
    total_trades: int
    win_rate: float
    profit_loss_ratio: float
    total_return_pct: float
    annualized_return_pct: float
    benchmark_return_pct: float
    alpha_pct: float
    max_drawdown_pct: float
    max_drawdown_days: int
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    winning_trades: int = 0
    losing_trades: int = 0
    avg_trade_pnl: float = 0.0
    avg_hold_bars: float = 0.0
    initial_capital: float = 1000000.0
    final_equity: float = 1000000.0
    effective_leverage: float = 1.0
    roll_trades: int = 0
    total_roll_yield_pct: float = 0.0
    roll_cost_total: float = 0.0
    roll_price_gap_total: float = 0.0
    roll_price_gap_pct: float = 0.0
    include_roll_cost: bool = True
    roll_model_status: str = "UNAVAILABLE"
    trade_logs: List[TradeRecord] = field(default_factory=list)
    daily_equity: List[Dict[str, Any]] = field(default_factory=list)
    strategy_name: str = "十四维全息融合策略"
    symbol: str = "CJ0"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategyName": self.strategy_name,
            "symbol": self.symbol,
            "initialCapital": round(self.initial_capital, 2),
            "finalEquity": round(self.final_equity, 2),
            "effectiveLeverage": round(self.effective_leverage, 2),
            "rollTrades": self.roll_trades,
            "totalRollYieldPct": round(self.total_roll_yield_pct, 2),
            "rollCostTotal": round(self.roll_cost_total, 2),
            "rollPriceGapTotal": round(self.roll_price_gap_total, 2),
            "rollPriceGapPct": round(self.roll_price_gap_pct, 4),
            "includeRollCost": self.include_roll_cost,
            "executionModel": "NEXT_BAR_OPEN",
            "rollModelStatus": self.roll_model_status,
            "limitations": [
                "日线模型按下一交易日开盘成交，不代表 Tick 级盘口必然成交",
                "历史手续费与保证金调整若上游未提供，采用天勤当前合约规格与用户参数中的较保守值",
                "结果为历史仿真，不代表实盘收益",
            ],
            "totalReturnPct": round(self.total_return_pct, 2),
            "annualizedReturnPct": round(self.annualized_return_pct, 2),
            "benchmarkReturnPct": round(self.benchmark_return_pct, 2),
            "alphaPct": round(self.alpha_pct, 2),
            "maxDrawdownPct": round(self.max_drawdown_pct, 2),
            "maxDrawdownDays": self.max_drawdown_days,
            "sharpeRatio": round(self.sharpe_ratio, 2),
            "sortinoRatio": round(self.sortino_ratio, 2),
            "calmarRatio": round(self.calmar_ratio, 2),
            "totalTrades": self.total_trades,
            "winningTrades": self.winning_trades,
            "losingTrades": self.losing_trades,
            "winRate": round(self.win_rate, 2),
            "profitLossRatio": round(self.profit_loss_ratio, 2),
            "avgTradePnl": round(self.avg_trade_pnl, 2),
            "avgHoldBars": round(self.avg_hold_bars, 1),
            "dailyEquity": self.daily_equity,
            "tradeLogs": [
                {
                    "timestamp": t.timestamp.strftime("%Y-%m-%d"),
                    "action": t.action,
                    "price": round(t.price, 2),
                    "positionPct": round(t.position_pct * 100, 1),
                    "pnl": round(t.pnl, 2),
                    "returnPct": round(t.return_pct, 2),
                    "reason": t.reason,
                    "holdBars": t.hold_bars,
                    "contract": t.contract,
                    "lots": t.lots,
                    "fee": round(t.fee, 2),
                    "slippageCost": round(t.slippage_cost, 2),
                    "fromContract": t.from_contract,
                    "toContract": t.to_contract,
                    "oldPrice": round(t.old_price, 2) if t.old_price is not None else None,
                    "newPrice": round(t.new_price, 2) if t.new_price is not None else None,
                    "priceGap": round(t.price_gap, 2) if t.price_gap is not None else None,
                }
                for t in self.trade_logs
            ],
        }


@dataclass(frozen=True)
class ExecutionFill:
    price: float
    lots: int
    fee: float
    slippage_cost: float
    contract: str
    raw_pnl: float = 0.0
    trade_net_pnl: float = 0.0


@dataclass(frozen=True)
class RollFill:
    from_contract: str
    to_contract: str
    old_price: float
    new_price: float
    lots: int
    fee: float
    slippage_cost: float
    realized_pnl: float
    cash_change: float
    price_gap: float
    price_gap_total: float


class FuturesExecutionLedger:
    """Integer-lot futures cash, margin and execution ledger."""

    def __init__(self, initial_cash: float):
        self.cash = float(initial_cash)
        self.direction = 0
        self.contract: str | None = None
        self.lots = 0
        self.entry_price = 0.0
        self.trade_cumulative_pnl = 0.0

    @staticmethod
    def _fill_price(market_price: float, order_direction: int,
                    spec: FuturesContractSpec, slippage_ticks: float) -> float:
        tick = spec.price_tick
        adverse = market_price + order_direction * max(0.0, slippage_ticks) * tick
        ticks = adverse / tick
        rounded_ticks = math.ceil(ticks - 1e-12) if order_direction > 0 else math.floor(ticks + 1e-12)
        return max(tick, rounded_ticks * tick)

    @staticmethod
    def _fee(price: float, lots: int, spec: FuturesContractSpec, fee_rate: float) -> float:
        provider_fee = spec.commission_per_lot * lots
        rate_fee = price * spec.volume_multiple * lots * max(0.0, fee_rate)
        return max(provider_fee, rate_fee)

    @staticmethod
    def _margin_per_lot(price: float, spec: FuturesContractSpec, margin_rate: float) -> float:
        rate_margin = price * spec.volume_multiple * margin_rate
        return max(spec.margin_per_lot, rate_margin)

    def open_position(
        self,
        *,
        direction: int,
        contract: str,
        market_price: float,
        spec: FuturesContractSpec,
        margin_rate: float,
        margin_budget_ratio: float,
        target_leverage: float,
        slippage_ticks: float,
        fee_rate: float,
    ) -> ExecutionFill:
        if self.direction != 0:
            raise ValueError("Cannot open a second futures position")
        fill_price = self._fill_price(market_price, direction, spec, slippage_ticks)
        max_by_margin = math.floor(
            self.cash * margin_budget_ratio / self._margin_per_lot(fill_price, spec, margin_rate)
        )
        max_by_notional = math.floor(
            self.cash * target_leverage / (fill_price * spec.volume_multiple)
        )
        lots = max(0, min(max_by_margin, max_by_notional))
        fee = self._fee(fill_price, lots, spec, fee_rate)
        slippage_cost = abs(fill_price - market_price) * spec.volume_multiple * lots
        if lots > 0:
            self.cash -= fee
            self.direction = 1 if direction > 0 else -1
            self.contract = contract
            self.lots = lots
            self.entry_price = fill_price
            self.trade_cumulative_pnl = -fee
        return ExecutionFill(fill_price, lots, fee, slippage_cost, contract)

    def close_position(
        self,
        *,
        market_price: float,
        spec: FuturesContractSpec,
        slippage_ticks: float,
        fee_rate: float,
    ) -> ExecutionFill:
        if self.direction == 0 or not self.contract:
            raise ValueError("No futures position to close")
        order_direction = -self.direction
        fill_price = self._fill_price(market_price, order_direction, spec, slippage_ticks)
        raw_pnl = self.direction * (fill_price - self.entry_price) * spec.volume_multiple * self.lots
        fee = self._fee(fill_price, self.lots, spec, fee_rate)
        slippage_cost = abs(fill_price - market_price) * spec.volume_multiple * self.lots
        self.cash += raw_pnl - fee
        self.trade_cumulative_pnl += raw_pnl - fee
        result = ExecutionFill(
            fill_price, self.lots, fee, slippage_cost, self.contract,
            raw_pnl=raw_pnl, trade_net_pnl=self.trade_cumulative_pnl,
        )
        self.direction = 0
        self.contract = None
        self.lots = 0
        self.entry_price = 0.0
        self.trade_cumulative_pnl = 0.0
        return result

    def roll_position(
        self,
        *,
        event: RollEvent,
        from_spec: FuturesContractSpec,
        to_spec: FuturesContractSpec,
        margin_rate: float,
        margin_budget_ratio: float,
        target_leverage: float,
        slippage_ticks: float,
        fee_rate: float,
    ) -> RollFill:
        if self.direction == 0 or self.contract != event.from_contract:
            raise ValueError("Roll event does not match the open contract")
        direction = self.direction
        old_lots = self.lots
        old_fill = self._fill_price(event.old_open, -direction, from_spec, slippage_ticks)
        realized = direction * (old_fill - self.entry_price) * from_spec.volume_multiple * old_lots
        close_fee = self._fee(old_fill, old_lots, from_spec, fee_rate)
        close_slippage = abs(old_fill - event.old_open) * from_spec.volume_multiple * old_lots
        self.cash += realized - close_fee
        self.trade_cumulative_pnl += realized - close_fee

        new_fill = self._fill_price(event.new_open, direction, to_spec, slippage_ticks)
        max_by_margin = math.floor(
            self.cash * margin_budget_ratio / self._margin_per_lot(new_fill, to_spec, margin_rate)
        )
        max_by_notional = math.floor(
            self.cash * target_leverage / (new_fill * to_spec.volume_multiple)
        )
        new_lots = max(0, min(old_lots, max_by_margin, max_by_notional))
        open_fee = self._fee(new_fill, new_lots, to_spec, fee_rate)
        open_slippage = abs(new_fill - event.new_open) * to_spec.volume_multiple * new_lots
        self.cash -= open_fee
        self.trade_cumulative_pnl -= open_fee

        self.contract = event.to_contract if new_lots > 0 else None
        self.lots = new_lots
        self.entry_price = new_fill if new_lots > 0 else 0.0
        self.direction = direction if new_lots > 0 else 0
        price_gap = new_fill - old_fill
        return RollFill(
            from_contract=event.from_contract,
            to_contract=event.to_contract,
            old_price=old_fill,
            new_price=new_fill,
            lots=new_lots,
            fee=close_fee + open_fee,
            slippage_cost=close_slippage + open_slippage,
            realized_pnl=realized,
            cash_change=realized - close_fee - open_fee,
            price_gap=price_gap,
            price_gap_total=price_gap * to_spec.volume_multiple * new_lots,
        )

    def unrealized_pnl(self, market_price: float, spec: FuturesContractSpec) -> float:
        if self.direction == 0:
            return 0.0
        return self.direction * (market_price - self.entry_price) * spec.volume_multiple * self.lots

    def equity(self, market_price: float, spec: FuturesContractSpec) -> float:
        return self.cash + self.unrealized_pnl(market_price, spec)

    def margin_occupied(self, market_price: float, spec: FuturesContractSpec, margin_rate: float) -> float:
        if self.direction == 0:
            return 0.0
        return self._margin_per_lot(market_price, spec, margin_rate) * self.lots


class QuantitativeBacktester:
    """专业多策略量化回测与模拟引擎"""

    def __init__(self, initial_capital: float = 1000000.0, margin_rate: float = 0.12):
        self.initial_capital = initial_capital
        self.margin_rate = margin_rate
        self.engine = HolisticFusionEngine()

    def run_backtest(
        self,
        klines: List[KLineBar],
        strategy: str = "HOLISTIC_14D",
        symbol: str = "CJ0",
        fee_rate: float = 0.0001,       # 手续费率万分之1
        slippage: float = 1.0,          # 滑点跳数/绝对点
        max_pos_ratio: float = 0.30,     # 单策略保证金占用比例 (默认 30%)
        stop_loss_atr: float = 2.0,     # ATR 跟踪止损倍数
        take_profit_atr: float = 4.0,   # ATR 止盈倍数
        margin_rate: float = 0.12,      # 期货基准保证金率 (默认 12%)
        leverage: Optional[float] = None, # 显式有效杠杆倍数 (若为 None 则自动按仓位/保证金率折算)
        include_roll_cost: bool = False,
        roll_events: list[RollEvent] | None = None,
        contract_specs: dict[str, FuturesContractSpec] | None = None,
        signal_klines: List[KLineBar] | None = None,
    ) -> BacktestResult:
        signal_klines = klines if signal_klines is None else signal_klines
        if [b.timestamp for b in signal_klines] != [b.timestamp for b in klines]:
            raise ValueError("Signal and execution bars must have identical timestamps")
        if any(a.timestamp >= b.timestamp for a, b in zip(klines, klines[1:])):
            raise ValueError("Backtest bars must be strictly ordered and unique")
        roll_events = roll_events or []
        contract_specs = contract_specs or {}
        bars_have_contracts = bool(klines) and all(bar.contract_symbol for bar in klines)
        include_roll_cost = bool(include_roll_cost and roll_events and bars_have_contracts)
        if include_roll_cost:
            roll_model_status = "TQSDK_REAL_DOMINANT_CONTRACTS"
        elif bars_have_contracts:
            roll_model_status = "NO_OBSERVED_ROLL_EVENTS"
        else:
            roll_model_status = "UNAVAILABLE_WITH_CONTINUOUS_DAILY_SERIES"

        if len(klines) < 25:
            return BacktestResult(
                total_trades=0, win_rate=0.0, profit_loss_ratio=0.0,
                total_return_pct=0.0, annualized_return_pct=0.0,
                benchmark_return_pct=0.0, alpha_pct=0.0,
                max_drawdown_pct=0.0, max_drawdown_days=0,
                sharpe_ratio=0.0, sortino_ratio=0.0, calmar_ratio=0.0,
                initial_capital=self.initial_capital, final_equity=self.initial_capital,
                effective_leverage=1.0, symbol=symbol,
                roll_trades=0, total_roll_yield_pct=0.0, roll_cost_total=0.0,
                include_roll_cost=include_roll_cost,
                roll_model_status=roll_model_status,
            )

        # 1. 真实有效杠杆计算 (基于期货交易保证金实务)
        # 投资者配置 30% 仓位资金用于缴纳 12% 保证金，实际头寸名义价值杠杆为 30% / 12% = 2.5x 杠杆
        pos_ratio = max_pos_ratio / 100.0 if max_pos_ratio > 1.0 else max_pos_ratio
        if strategy == "BUY_AND_HOLD":
            effective_leverage = 1.0
        elif leverage is not None and leverage > 0:
            effective_leverage = float(leverage)
        else:
            effective_leverage = max(1.0, min(5.0, pos_ratio / max(0.05, margin_rate)))

        ledger = FuturesExecutionLedger(self.initial_capital)
        capital = ledger.cash
        peak_capital = capital
        max_drawdown = 0.0
        drawdown_duration = 0
        current_dd_days = 0

        # 持仓状态: 1 = 做多, -1 = 做空, 0 = 空仓
        position_direction = 0
        entry_price = 0.0
        entry_bar_idx = 0
        trailing_stop_price = 0.0
        trailing_peak_price = 0.0

        roll_trades_count = 0
        total_roll_yield_amount = 0.0
        total_roll_friction = 0.0
        total_roll_price_gap = 0.0
        roll_by_date = {event.execution_date: event for event in roll_events}

        def spec_for(contract: str | None) -> FuturesContractSpec:
            if contract and contract in contract_specs:
                return contract_specs[contract]
            # Compatibility path for legacy data. It never claims to model a
            # real roll because include_roll_cost is disabled without tags.
            return FuturesContractSpec(
                contract=contract or symbol,
                volume_multiple=1,
                price_tick=1.0,
                margin_per_lot=0.0,
                commission_per_lot=0.0,
            )

        trades: List[TradeRecord] = []
        daily_equity_curve: List[Dict[str, Any]] = []
        daily_returns: List[float] = []

        winning_trades = 0
        losing_trades = 0
        total_profit = 0.0
        total_loss = 0.0
        total_hold_days = 0

        def close_position(market_price: float, reason: str, fill_bar: KLineBar, hold_bars: int) -> None:
            nonlocal capital, position_direction, winning_trades, losing_trades
            nonlocal total_profit, total_loss, total_hold_days
            direction = ledger.direction
            close_fill = ledger.close_position(
                market_price=market_price, spec=spec_for(ledger.contract),
                slippage_ticks=slippage, fee_rate=fee_rate,
            )
            capital = ledger.cash
            net_pnl = close_fill.trade_net_pnl
            trades.append(TradeRecord(
                timestamp=fill_bar.timestamp,
                action="FLATTEN_LONG" if direction > 0 else "FLATTEN_SHORT",
                price=close_fill.price, position_pct=0.0, pnl=net_pnl,
                return_pct=net_pnl / self.initial_capital * 100.0,
                reason=reason, hold_bars=hold_bars, contract=close_fill.contract,
                lots=close_fill.lots, fee=close_fill.fee, slippage_cost=close_fill.slippage_cost,
            ))
            if net_pnl > 0:
                winning_trades += 1
                total_profit += net_pnl
            else:
                losing_trades += 1
                total_loss += abs(net_pnl)
            total_hold_days += hold_bars
            position_direction = 0

        closes = [b.close for b in signal_klines]
        highs = [b.high for b in signal_klines]
        lows = [b.low for b in signal_klines]
        vols = [b.volume for b in signal_klines]

        # 预计算 ATR(14)
        tr_list = [highs[0] - lows[0]]
        for j in range(1, len(klines)):
            tr_list.append(max(
                highs[j] - lows[j],
                abs(highs[j] - closes[j - 1]),
                abs(lows[j] - closes[j - 1]),
            ))
        atr14_series = [sum(tr_list[:14]) / 14.0] * 14
        for j in range(14, len(klines)):
            atr14_series.append(sum(tr_list[j-13:j+1]) / 14.0)

        # 预计算移动均线 MA5, MA10, MA15, MA20, MA60, EMA12, EMA26
        def calc_ma(series: List[float], n: int) -> List[float]:
            res = []
            for idx in range(len(series)):
                if idx < n:
                    res.append(sum(series[:idx+1]) / (idx + 1))
                else:
                    res.append(sum(series[idx-n+1:idx+1]) / float(n))
            return res

        def calc_ema(series: List[float], n: int) -> List[float]:
            res = [series[0]]
            alpha = 2.0 / (n + 1.0)
            for v in series[1:]:
                res.append(alpha * v + (1.0 - alpha) * res[-1])
            return res

        ma5 = calc_ma(closes, 5)
        ma10 = calc_ma(closes, 10)
        ma15 = calc_ma(closes, 15)
        ma20 = calc_ma(closes, 20)
        ma60 = calc_ma(closes, 60)
        ema12 = calc_ema(closes, 12)
        ema20 = calc_ema(closes, 20)
        ema26 = calc_ema(closes, 26)

        strat_names = {
            "HOLISTIC_14D": "十四维全息融合策略",
            "MOMENTUM_BREAKOUT": "唐奇安通道放量动量突破",
            "BOLLINGER_REVERSAL": "布林带自适应均值回归",
            "DUAL_THRUST": "经典 Dual Thrust 区间突破",
            "ADAPTIVE_CTA": "全天候自适应趋势CTA策略",
            "BUY_AND_HOLD": "标的买入持有基准",
        }
        strat_display_name = strat_names.get(strategy, "十四维全息融合策略")

        # 起始安全周期 (确保有充足历史K线计算MA60和ATR)
        start_idx = 60 if (strategy in ("HOLISTIC_14D", "MOMENTUM_BREAKOUT", "DUAL_THRUST", "ADAPTIVE_CTA") and len(klines) >= 65) else 20
        benchmark_equity = self.initial_capital

        # Signals are calculated from bar[i] only after it has closed, then filled
        # at bar[i + 1].open. This prevents same-close look-ahead bias.
        for execution_idx in range(start_idx + 1, len(klines)):
            i = execution_idx - 1
            bar = signal_klines[i]
            fill_bar = klines[execution_idx]
            prev_bar = signal_klines[i - 1]
            cur_atr = atr14_series[i]

            signal = "HOLD"
            action_desc = "观望"
            current_roll = roll_by_date.get(fill_bar.timestamp.date()) if include_roll_cost else None
            opened_today = False

            # ---------------- 2. 策略信号发生器 ----------------
            if strategy == "HOLISTIC_14D":
                sub_klines = signal_klines[:i + 1]
                chg = bar.close - prev_bar.close
                chg_pct = (chg / prev_bar.close) * 100.0 if prev_bar.close > 0 else 0.0
                sim_quote = MarketQuote(
                    symbol=symbol,
                    name=symbol,
                    price=bar.close,
                    change=chg,
                    change_pct=chg_pct,
                    open=bar.open,
                    high=bar.high,
                    low=bar.low,
                    prev_close=prev_bar.close,
                    prev_settlement=prev_bar.close,
                    volume=bar.volume,
                    turnover=bar.volume * bar.close * 5.0,
                    open_interest=bar.open_interest,
                    timestamp=bar.timestamp,
                )
                ctx = {
                    "klines": sub_klines,
                    "quote": sim_quote,
                    "analysis_time": bar.timestamp,
                }
                decision = self.engine.evaluate_all(ctx)
                score = decision.composite_score
                res = decision.directional_resonance

                trend_up = bar.close > ma60[i]
                trend_down = bar.close < ma60[i]

                # 进场信号：十四维综合打分绝对值>=28，且共振度>=0.65，且与MA60大周期趋势一致
                if position_direction == 0:
                    if score >= 28.0 and trend_up and res >= 0.65:
                        signal = "BUY"
                        action_desc = f"十四维多头共振(+{score:.1f}分, 共振度{res:.2f})"
                    elif score <= -28.0 and trend_down and res >= 0.65:
                        signal = "SELL"
                        action_desc = f"十四维空头共振({score:.1f}分, 共振度{res:.2f})"
                elif position_direction > 0:
                    if score < 0.0 or bar.close < ma20[i]:
                        signal = "FLATTEN"
                        action_desc = f"十四维多头动能衰竭({score:+.1f}分)平多"
                elif position_direction < 0:
                    if score > 0.0 or bar.close > ma20[i]:
                        signal = "FLATTEN"
                        action_desc = f"十四维空头动能衰竭({score:+.1f}分)平空"

            elif strategy == "MOMENTUM_BREAKOUT":
                # 动量突破：20日高低点突破 + 均线大趋势顺势过滤 + 放量确认
                hh20 = max(highs[i-20:i])
                ll20 = min(lows[i-20:i])
                avg_vol_10 = sum(vols[i-10:i]) / 10.0 if i >= 10 else vols[i]
                vol_ok = bar.volume > avg_vol_10 * 1.05

                trend_up = bar.close > ma60[i]
                trend_down = bar.close < ma60[i]

                if position_direction == 0:
                    if bar.close > hh20 and trend_up and vol_ok:
                        signal = "BUY"
                        action_desc = "放量向上突破20日高点(顺MA60主趋势)"
                    elif bar.close < ll20 and trend_down and vol_ok:
                        signal = "SELL"
                        action_desc = "放量向下跌破20日低点(顺MA60主趋势)"
                elif position_direction > 0 and bar.close < ma20[i]:
                    signal = "FLATTEN"
                    action_desc = "跌破MA20趋势线平多止盈"
                elif position_direction < 0 and bar.close > ma20[i]:
                    signal = "FLATTEN"
                    action_desc = "突破MA20趋势线平空止盈"

            elif strategy == "BOLLINGER_REVERSAL":
                # 布林带均值回归：15日窗口，2.2倍标准差，回归MA15中轨止盈，硬ATR止损
                sub_closes = closes[max(0, i-14):i+1]
                m = ma15[i]
                std = math.sqrt(sum((c - m) ** 2 for c in sub_closes) / len(sub_closes)) if len(sub_closes) > 1 else 1.0
                upper_boll = m + 2.2 * std
                lower_boll = m - 2.2 * std

                if position_direction == 0:
                    if bar.close <= lower_boll:
                        signal = "BUY"
                        action_desc = f"触及布林超跌下轨({lower_boll:.1f})超卖反弹做多"
                    elif bar.close >= upper_boll:
                        signal = "SELL"
                        action_desc = f"触及布林超买上轨({upper_boll:.1f})超买回落做空"
                elif position_direction > 0 and bar.close >= m:
                    signal = "FLATTEN"
                    action_desc = f"价格回归布林中轨({m:.1f})多头止盈"
                elif position_direction < 0 and bar.close <= m:
                    signal = "FLATTEN"
                    action_desc = f"价格回归布林中轨({m:.1f})空头止盈"

            elif strategy == "DUAL_THRUST":
                lookback = 4
                hh = max(highs[i-lookback:i])
                hc = max(closes[i-lookback:i])
                ll = min(lows[i-lookback:i])
                lc = min(closes[i-lookback:i])
                rng = max(hh - lc, hc - ll)
                k1, k2 = 0.5, 0.5
                buy_trig = bar.open + k1 * rng
                sell_trig = bar.open - k2 * rng

                trend_up = bar.close > ma60[i]
                trend_down = bar.close < ma60[i]

                if position_direction == 0:
                    if bar.close > buy_trig and trend_up:
                        signal = "BUY"
                        action_desc = "突破Dual Thrust上轨(顺MA60趋势)"
                    elif bar.close < sell_trig and trend_down:
                        signal = "SELL"
                        action_desc = "跌破Dual Thrust下轨(顺MA60趋势)"
                elif position_direction > 0 and bar.close < ma10[i]:
                    signal = "FLATTEN"
                    action_desc = "跌破MA10短周期均线平多"
                elif position_direction < 0 and bar.close > ma10[i]:
                    signal = "FLATTEN"
                    action_desc = "突破MA10短周期均线平空"

            elif strategy == "ADAPTIVE_CTA":
                # 全天候自适应趋势CTA策略 (肯特纳通道突破 + EMA60 宏观大趋势)
                kc_up = ema20[i] + 1.8 * cur_atr
                kc_dn = ema20[i] - 1.8 * cur_atr
                trend_up = bar.close > ma60[i]
                trend_down = bar.close < ma60[i]

                if position_direction == 0:
                    if bar.close > kc_up and trend_up:
                        signal = "BUY"
                        action_desc = "突破肯特纳上轨(顺MA60宏观趋势)"
                    elif bar.close < kc_dn and trend_down:
                        signal = "SELL"
                        action_desc = "跌破肯特纳下轨(顺MA60宏观趋势)"
                elif position_direction > 0 and bar.close < ema20[i]:
                    signal = "FLATTEN"
                    action_desc = "回落跌破EMA20均线平多"
                elif position_direction < 0 and bar.close > ema20[i]:
                    signal = "FLATTEN"
                    action_desc = "反弹突破EMA20均线平空"

            elif strategy == "BUY_AND_HOLD":
                if i == start_idx:
                    signal = "BUY"
                    action_desc = "标的买入持有基准"

            # ---------------- 3. 开盘交易与换月结算 ----------------
            hold_bars = execution_idx - entry_bar_idx if position_direction != 0 else 0

            # 平仓结算
            if (signal in ("FLATTEN", "SELL") and position_direction > 0) or \
               (signal in ("FLATTEN", "BUY") and position_direction < 0):
                price = (current_roll.old_open
                         if current_roll and ledger.contract == current_roll.from_contract
                         else fill_bar.open)
                close_position(price, action_desc, fill_bar, hold_bars)

            # A still-open position must be closed in the old delivery month
            # and reopened in the new one. The quoted gap is a basis reset,
            # never an immediate cash profit or loss.
            if (
                current_roll
                and ledger.direction != 0
                and ledger.contract == current_roll.from_contract
            ):
                opened_today = True
                roll_direction = ledger.direction
                roll_fill = ledger.roll_position(
                    event=current_roll,
                    from_spec=spec_for(current_roll.from_contract),
                    to_spec=spec_for(current_roll.to_contract),
                    margin_rate=margin_rate,
                    margin_budget_ratio=pos_ratio,
                    target_leverage=effective_leverage,
                    slippage_ticks=slippage,
                    fee_rate=fee_rate,
                )
                capital = ledger.cash
                position_direction = ledger.direction
                entry_price = ledger.entry_price
                trailing_peak_price = entry_price
                trailing_stop_price = (
                    entry_price - stop_loss_atr * cur_atr
                    if position_direction > 0
                    else entry_price + stop_loss_atr * cur_atr
                )
                roll_trades_count += 1
                roll_friction = roll_fill.fee + roll_fill.slippage_cost
                total_roll_friction += roll_friction
                total_roll_price_gap += roll_fill.price_gap_total
                trades.append(TradeRecord(
                    timestamp=fill_bar.timestamp,
                    action="ROLL_LONG" if roll_direction > 0 else "ROLL_SHORT",
                    price=roll_fill.new_price,
                    position_pct=pos_ratio if roll_direction > 0 else -pos_ratio,
                    pnl=roll_fill.cash_change,
                    return_pct=roll_fill.cash_change / self.initial_capital * 100.0,
                    reason=(
                        "真实主力换月：平旧合约、开新合约；"
                        "价差仅重置持仓成本基准，不直接计入权益"
                    ),
                    hold_bars=hold_bars,
                    contract=roll_fill.to_contract,
                    lots=roll_fill.lots,
                    fee=roll_fill.fee,
                    slippage_cost=roll_fill.slippage_cost,
                    from_contract=roll_fill.from_contract,
                    to_contract=roll_fill.to_contract,
                    old_price=roll_fill.old_price,
                    new_price=roll_fill.new_price,
                    price_gap=roll_fill.price_gap,
                ))

            # 开仓结算
            if signal == "BUY" and position_direction == 0:
                contract = fill_bar.contract_symbol or symbol
                open_fill = ledger.open_position(
                    direction=1,
                    contract=contract,
                    market_price=fill_bar.open,
                    spec=spec_for(contract),
                    margin_rate=margin_rate,
                    margin_budget_ratio=pos_ratio,
                    target_leverage=effective_leverage,
                    slippage_ticks=slippage,
                    fee_rate=fee_rate,
                )
                capital = ledger.cash
                if open_fill.lots > 0:
                    position_direction = 1
                    entry_price = open_fill.price
                    opened_today = True
                    entry_bar_idx = execution_idx
                    trailing_peak_price = entry_price
                    trailing_stop_price = entry_price - stop_loss_atr * cur_atr
                    trades.append(TradeRecord(
                        timestamp=fill_bar.timestamp,
                        action="OPEN_BUY",
                        price=entry_price,
                        position_pct=pos_ratio,
                        pnl=-open_fill.fee,
                        return_pct=-open_fill.fee / self.initial_capital * 100.0,
                        reason=action_desc,
                        hold_bars=0,
                        contract=open_fill.contract,
                        lots=open_fill.lots,
                        fee=open_fill.fee,
                        slippage_cost=open_fill.slippage_cost,
                    ))
            elif signal == "SELL" and position_direction == 0 and strategy != "BUY_AND_HOLD":
                contract = fill_bar.contract_symbol or symbol
                open_fill = ledger.open_position(
                    direction=-1,
                    contract=contract,
                    market_price=fill_bar.open,
                    spec=spec_for(contract),
                    margin_rate=margin_rate,
                    margin_budget_ratio=pos_ratio,
                    target_leverage=effective_leverage,
                    slippage_ticks=slippage,
                    fee_rate=fee_rate,
                )
                capital = ledger.cash
                if open_fill.lots > 0:
                    position_direction = -1
                    entry_price = open_fill.price
                    opened_today = True
                    entry_bar_idx = execution_idx
                    trailing_peak_price = entry_price
                    trailing_stop_price = entry_price + stop_loss_atr * cur_atr
                    trades.append(TradeRecord(
                        timestamp=fill_bar.timestamp,
                        action="OPEN_SHORT",
                        price=entry_price,
                        position_pct=-pos_ratio,
                        pnl=-open_fill.fee,
                        return_pct=-open_fill.fee / self.initial_capital * 100.0,
                        reason=action_desc,
                        hold_bars=0,
                        contract=open_fill.contract,
                        lots=open_fill.lots,
                        fee=open_fill.fee,
                        slippage_cost=open_fill.slippage_cost,
                    ))

            # Opening fills and rolls happen before intraday risk. In particular,
            # the new contract's daily range cannot stop an already-closed old leg.
            if ledger.direction and fill_bar.contract_symbol and ledger.contract != fill_bar.contract_symbol:
                raise ValueError("Held contract has no matching observed execution bar")
            stop_fill_price = None
            # ---------------- 4. 成交后的日内止损监控 ----------------
            if position_direction != 0 and stop_loss_atr > 0 and strategy != "BUY_AND_HOLD":
                if strategy == "BOLLINGER_REVERSAL":
                    # 布林带均值回归使用固定硬止损保护，不使用提前移动跟踪止损以保障中轨回归率
                    if position_direction > 0 and fill_bar.low <= trailing_stop_price:
                        signal = "FLATTEN"
                        action_desc = f"触发布林硬止损保护({trailing_stop_price:.1f})"
                        stop_fill_price = min(fill_bar.open, trailing_stop_price)
                    elif position_direction < 0 and fill_bar.high >= trailing_stop_price:
                        signal = "FLATTEN"
                        action_desc = f"触发布林空头硬止损保护({trailing_stop_price:.1f})"
                        stop_fill_price = max(fill_bar.open, trailing_stop_price)
                else:
                    # 趋势类策略使用 ATR 吊灯移动跟踪止盈 (Chandelier Exit)
                    if position_direction > 0:
                        if not opened_today:
                            trailing_peak_price = max(trailing_peak_price, klines[i].high)
                        hard_stop = entry_price - stop_loss_atr * cur_atr
                        if trailing_peak_price >= entry_price + 2.0 * cur_atr:
                            trail_stop = trailing_peak_price - (take_profit_atr if take_profit_atr > 0 else 3.5) * cur_atr
                            eff_stop = max(hard_stop, trail_stop, entry_price + 0.2 * cur_atr)
                        else:
                            eff_stop = hard_stop

                        if fill_bar.low <= eff_stop:
                            signal = "FLATTEN"
                            action_desc = f"触发ATR移动跟踪止损({eff_stop:.1f})"
                            stop_fill_price = min(fill_bar.open, eff_stop)
                    elif position_direction < 0:
                        if not opened_today:
                            trailing_peak_price = min(trailing_peak_price, klines[i].low)
                        hard_stop = entry_price + stop_loss_atr * cur_atr
                        if trailing_peak_price <= entry_price - 2.0 * cur_atr:
                            trail_stop = trailing_peak_price + (take_profit_atr if take_profit_atr > 0 else 3.5) * cur_atr
                            eff_stop = min(hard_stop, trail_stop, entry_price - 0.2 * cur_atr)
                        else:
                            eff_stop = hard_stop

                        if fill_bar.high >= eff_stop:
                            signal = "FLATTEN"
                            action_desc = f"触发ATR空头移动跟踪止损({eff_stop:.1f})"
                            stop_fill_price = max(fill_bar.open, eff_stop)

            if stop_fill_price is not None:
                close_position(stop_fill_price, action_desc, fill_bar,
                               execution_idx - entry_bar_idx)

            # ---------------- 5. 计算当日动态权益与回撤 ----------------
            if position_direction != 0:
                current_spec = spec_for(ledger.contract)
                current_equity = ledger.equity(fill_bar.close, current_spec)
                margin_occupied = ledger.margin_occupied(fill_bar.close, current_spec, margin_rate)
            else:
                current_equity = ledger.cash
                margin_occupied = 0.0
            peak_capital = max(peak_capital, current_equity)
            dd_pct = (peak_capital - current_equity) / peak_capital * 100.0 if peak_capital > 0 else 0.0
            max_drawdown = max(max_drawdown, dd_pct)

            if dd_pct > 0.05:
                current_dd_days += 1
                drawdown_duration = max(drawdown_duration, current_dd_days)
            else:
                current_dd_days = 0

            # 基准也按真实换月路径计算，消除连续合约拼接价差造成的虚假跳变。
            if current_roll:
                overnight_leg = current_roll.old_open / klines[i].close if klines[i].close > 0 else 1.0
                intraday_leg = fill_bar.close / current_roll.new_open if current_roll.new_open > 0 else 1.0
                benchmark_equity *= overnight_leg * intraday_leg
            elif klines[i].close > 0:
                benchmark_equity *= fill_bar.close / klines[i].close

            prev_eq = daily_equity_curve[-1]["equity"] if daily_equity_curve else self.initial_capital
            daily_ret = ((current_equity / prev_eq) - 1.0) * 100.0
            daily_returns.append(daily_ret)

            cash_avail = max(0.0, current_equity - margin_occupied)
            actual_position_pct = (
                position_direction * margin_occupied / current_equity * 100.0
                if current_equity > 0 and position_direction != 0
                else 0.0
            )

            daily_equity_curve.append({
                "date": fill_bar.timestamp.strftime("%Y-%m-%d"),
                "equity": round(current_equity, 2),
                "benchmarkEquity": round(benchmark_equity, 2),
                "cash": round(cash_avail, 2),
                "positionPct": round(actual_position_pct, 1),
                "dailyReturnPct": round(daily_ret, 2),
                "drawdownPct": round(dd_pct, 2),
            })

        # 回测期末强制平仓结算
        if position_direction != 0 and len(klines) > 0:
            final_bar = klines[-1]
            close_fill = ledger.close_position(
                market_price=final_bar.close,
                spec=spec_for(ledger.contract),
                slippage_ticks=slippage,
                fee_rate=fee_rate,
            )
            capital = ledger.cash
            net_pnl = close_fill.trade_net_pnl
            ret_pct = net_pnl / self.initial_capital * 100.0
            hold_bars = len(klines) - entry_bar_idx

            trades.append(TradeRecord(
                timestamp=final_bar.timestamp,
                action="FINAL_FLATTEN",
                price=close_fill.price,
                position_pct=0.0,
                pnl=net_pnl,
                return_pct=ret_pct,
                reason="回测期末强制平仓结算",
                hold_bars=hold_bars,
                contract=close_fill.contract,
                lots=close_fill.lots,
                fee=close_fill.fee,
                slippage_cost=close_fill.slippage_cost,
            ))
            if net_pnl > 0:
                winning_trades += 1
                total_profit += net_pnl
            else:
                losing_trades += 1
                total_loss += abs(net_pnl)
            total_hold_days += hold_bars
            position_direction = 0

            if daily_equity_curve:
                previous_equity = (
                    daily_equity_curve[-2]["equity"]
                    if len(daily_equity_curve) > 1
                    else self.initial_capital
                )
                final_daily_return = ((capital / previous_equity) - 1.0) * 100.0
                peak_capital = max(peak_capital, capital)
                final_drawdown = (
                    (peak_capital - capital) / peak_capital * 100.0
                    if peak_capital > 0
                    else 0.0
                )
                max_drawdown = max(max_drawdown, final_drawdown)
                daily_equity_curve[-1].update({
                    "equity": round(capital, 2),
                    "cash": round(capital, 2),
                    "positionPct": 0.0,
                    "dailyReturnPct": round(final_daily_return, 2),
                    "drawdownPct": round(final_drawdown, 2),
                })
                if daily_returns:
                    daily_returns[-1] = final_daily_return

        # ---------------- 6. 统计绩效指标计算 ----------------
        total_trades = winning_trades + losing_trades
        win_rate = (winning_trades / total_trades * 100.0) if total_trades > 0 else 0.0
        avg_profit = total_profit / max(1, winning_trades)
        avg_loss = total_loss / max(1, losing_trades)
        pl_ratio = (avg_profit / avg_loss) if avg_loss > 0 else (3.0 if avg_profit > 0 else 1.0)
        total_return_pct = (capital - self.initial_capital) / self.initial_capital * 100.0

        trading_days = max(1, len(daily_equity_curve))
        years = trading_days / 250.0
        if capital > 0 and years > 0:
            annualized_return_pct = ((capital / self.initial_capital) ** (1.0 / years) - 1.0) * 100.0
        else:
            annualized_return_pct = total_return_pct

        benchmark_return_pct = (benchmark_equity / self.initial_capital - 1.0) * 100.0
        alpha_pct = total_return_pct - benchmark_return_pct

        if daily_returns:
            mean_ret = sum(daily_returns) / len(daily_returns)
            var_ret = sum((r - mean_ret) ** 2 for r in daily_returns) / len(daily_returns)
            std_ret = math.sqrt(var_ret)
            downside_var = sum((min(0.0, r)) ** 2 for r in daily_returns) / len(daily_returns)
            downside_std = math.sqrt(downside_var)

            annual_factor = math.sqrt(250.0)
            sharpe = (mean_ret / std_ret * annual_factor) if std_ret > 0 else 0.0
            sortino = (mean_ret / downside_std * annual_factor) if downside_std > 0 else 0.0
        else:
            sharpe = 0.0
            sortino = 0.0

        calmar = (annualized_return_pct / max(1.0, max_drawdown)) if max_drawdown > 0 else 0.0
        total_roll_yield_pct = (total_roll_yield_amount / self.initial_capital) * 100.0 if self.initial_capital > 0 else 0.0
        roll_price_gap_pct = (total_roll_price_gap / self.initial_capital) * 100.0 if self.initial_capital > 0 else 0.0

        return BacktestResult(
            total_trades=total_trades,
            win_rate=round(win_rate, 1),
            profit_loss_ratio=round(pl_ratio, 2),
            total_return_pct=round(total_return_pct, 2),
            annualized_return_pct=round(annualized_return_pct, 2),
            benchmark_return_pct=round(benchmark_return_pct, 2),
            alpha_pct=round(alpha_pct, 2),
            max_drawdown_pct=round(max_drawdown, 2),
            max_drawdown_days=drawdown_duration,
            sharpe_ratio=round(sharpe, 2),
            sortino_ratio=round(sortino, 2),
            calmar_ratio=round(calmar, 2),
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            avg_trade_pnl=round((total_profit - total_loss) / max(1, total_trades), 2),
            avg_hold_bars=round(total_hold_days / max(1, total_trades), 1),
            initial_capital=self.initial_capital,
            final_equity=round(capital, 2),
            effective_leverage=round(effective_leverage, 2),
            roll_trades=roll_trades_count,
            total_roll_yield_pct=round(total_roll_yield_pct, 2),
            roll_cost_total=round(total_roll_friction, 2),
            roll_price_gap_total=round(total_roll_price_gap, 2),
            roll_price_gap_pct=round(roll_price_gap_pct, 4),
            include_roll_cost=include_roll_cost,
            roll_model_status=roll_model_status,
            trade_logs=trades,
            daily_equity=daily_equity_curve,
            strategy_name=strat_display_name,
            symbol=symbol,
        )


backtester = QuantitativeBacktester()
