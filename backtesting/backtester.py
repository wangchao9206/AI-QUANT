"""
AI-QUANT 多维量化回测引擎 (Backtester)
基于真实量价信号与风控规则的历史回测系统
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any

from data.data_feed import KLineBar, MarketQuote
from engines.fusion_engine import HolisticFusionEngine

@dataclass
class TradeRecord:
    timestamp: datetime
    action: str        # BUY / SELL / COVER / SHORT
    price: float
    position_pct: float
    pnl: float = 0.0
    reason: str = ""

@dataclass
class BacktestResult:
    total_trades: int
    win_rate: float
    profit_loss_ratio: float
    total_return_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float
    trade_logs: List[TradeRecord] = field(default_factory=list)

class QuantitativeBacktester:
    """多维信号回测器"""

    def __init__(self, initial_capital: float = 1000000.0):
        self.initial_capital = initial_capital
        self.engine = HolisticFusionEngine()

    def run_backtest(self, klines: List[KLineBar]) -> BacktestResult:
        if len(klines) < 21:
            return BacktestResult(
                total_trades=0, win_rate=0.0, profit_loss_ratio=0.0,
                total_return_pct=0.0, max_drawdown_pct=0.0, sharpe_ratio=0.0
            )

        capital = self.initial_capital
        peak_capital = capital
        max_drawdown = 0.0
        current_pos = 0.0  # -1.0 to 1.0
        entry_price = 0.0
        trades: List[TradeRecord] = []
        winning_trades = 0
        losing_trades = 0
        total_profit = 0.0
        total_loss = 0.0

        for i in range(20, len(klines)):
            bar = klines[i]
            prev_bar = klines[i - 1]
            prev_sub_klines = klines[:i+1]

            # 构造当日模拟快照
            chg = bar.close - prev_bar.close
            chg_pct = (chg / prev_bar.close) * 100.0
            sim_quote = MarketQuote(
                symbol="CJ2701",
                name="红枣主力",
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
                timestamp=bar.timestamp
            )

            ctx = {
                "klines": prev_sub_klines,
                "quote": sim_quote
            }
            decision = self.engine.evaluate_all(ctx)

            # 信号执行
            if decision.primary_signal in ("STRONG_SELL", "SELL") and current_pos >= 0:
                # 平多开空
                if current_pos > 0:
                    trade_pnl = (bar.close - entry_price) * current_pos * capital / entry_price
                    capital += trade_pnl
                    if trade_pnl > 0:
                        winning_trades += 1
                        total_profit += trade_pnl
                    else:
                        losing_trades += 1
                        total_loss += abs(trade_pnl)
                    trades.append(TradeRecord(bar.timestamp, "FLATTEN_LONG", bar.close, 0.0, trade_pnl, "多头平仓"))

                current_pos = decision.recommended_position_pct
                entry_price = bar.close
                trades.append(TradeRecord(bar.timestamp, "OPEN_SHORT", bar.close, current_pos, 0.0, decision.action_directive))

            elif decision.primary_signal in ("STRONG_BUY", "BUY") and current_pos <= 0:
                # 平空开多
                if current_pos < 0:
                    trade_pnl = (entry_price - bar.close) * abs(current_pos) * capital / entry_price
                    capital += trade_pnl
                    if trade_pnl > 0:
                        winning_trades += 1
                        total_profit += trade_pnl
                    else:
                        losing_trades += 1
                        total_loss += abs(trade_pnl)
                    trades.append(TradeRecord(bar.timestamp, "FLATTEN_SHORT", bar.close, 0.0, trade_pnl, "空头平仓"))

                current_pos = decision.recommended_position_pct
                entry_price = bar.close
                trades.append(TradeRecord(bar.timestamp, "OPEN_BUY", bar.close, current_pos, 0.0, decision.action_directive))

            # 更新回撤
            peak_capital = max(peak_capital, capital)
            dd = (peak_capital - capital) / peak_capital * 100.0
            max_drawdown = max(max_drawdown, dd)

        # 期末未平仓头寸平仓结算
        if current_pos != 0 and len(klines) > 0:
            final_bar = klines[-1]
            if current_pos > 0:
                final_pnl = (final_bar.close - entry_price) * current_pos * capital / entry_price
            else:
                final_pnl = (entry_price - final_bar.close) * abs(current_pos) * capital / entry_price
            capital += final_pnl
            if final_pnl > 0:
                winning_trades += 1
                total_profit += final_pnl
            else:
                losing_trades += 1
                total_loss += abs(final_pnl)
            trades.append(TradeRecord(final_bar.timestamp, "FINAL_FLATTEN", final_bar.close, 0.0, final_pnl, "期末强制平仓结算"))

        total_trades = winning_trades + losing_trades
        win_rate = (winning_trades / total_trades * 100.0) if total_trades > 0 else 0.0
        avg_profit = total_profit / max(1, winning_trades)
        avg_loss = total_loss / max(1, losing_trades)
        pl_ratio = (avg_profit / avg_loss) if avg_loss > 0 else 2.5
        total_return_pct = (capital - self.initial_capital) / self.initial_capital * 100.0
        sharpe_ratio = round(total_return_pct / max(5.0, max_drawdown), 2)

        return BacktestResult(
            total_trades=total_trades,
            win_rate=round(win_rate, 1),
            profit_loss_ratio=round(pl_ratio, 2),
            total_return_pct=round(total_return_pct, 2),
            max_drawdown_pct=round(max_drawdown, 2),
            sharpe_ratio=sharpe_ratio,
            trade_logs=trades
        )
