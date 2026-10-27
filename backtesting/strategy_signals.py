"""Daily entry/exit rules shared by retrospective and paper execution.

Callers pass only observations known at the decision clock. Execution, account
risk, fees and protective orders belong to their respective ledgers.
"""
from dataclasses import dataclass
from typing import Sequence
import math

from data.data_feed import KLineBar, MarketQuote
from engines.fusion_engine import HolisticFusionEngine

STRATEGY_NAMES = {
    'HOLISTIC_14D': '十四维全息融合',
    'MOMENTUM_BREAKOUT': '放量通道突破',
    'BOLLINGER_REVERSAL': '布林均值回归',
    'DUAL_THRUST': 'Dual Thrust 区间突破',
    'ADAPTIVE_CTA': '自适应趋势 CTA',
    'BUY_AND_HOLD': '买入持有基准',
}


@dataclass(frozen=True)
class DailySignal:
    signal: str
    reason: str
    atr: float
    required_bars: int = 20
    node_trace: list[dict] | None = None


def daily_atr(bars: Sequence[KLineBar], *, contract_aware: bool = False) -> float:
    if not bars:
        return 0.0
    values = [max(b.high-b.low, abs(b.high-bars[i-1].close), abs(b.low-bars[i-1].close))
              if i and not (contract_aware and b.contract_symbol != bars[i-1].contract_symbol)
              else b.high-b.low for i, b in enumerate(bars)]
    return sum(values[-14:]) / min(14, len(values))


def daily_signal(strategy: str, bars: Sequence[KLineBar], direction: int = 0,
                 symbol: str = '', *, first_entry: bool = True,
                 engine: HolisticFusionEngine | None = None,
                 enforce_warmup: bool = True, workflow=None) -> DailySignal:
    if strategy == 'WORKFLOW':
        from backtesting.workflow import Prepared, compile_workflow
        prepared = workflow if isinstance(workflow,Prepared) else compile_workflow(workflow).prepare(list(bars))
        outcome=prepared.evaluate(len(bars)-1,direction,first_entry=first_entry,symbol=symbol)
        return DailySignal(outcome.signal,outcome.reason,daily_atr(bars),outcome.required_bars,outcome.node_trace)
    if strategy not in STRATEGY_NAMES:
        raise ValueError('不支持的模拟策略')
    required = 2 if strategy == 'BUY_AND_HOLD' else 20 if strategy == 'BOLLINGER_REVERSAL' else 61
    atr = daily_atr(bars)
    if len(bars) < (required if enforce_warmup else 20):
        return DailySignal('WARMING', f'需要{required}根已完成日线，当前{len(bars)}根', atr, required)
    bar = bars[-1]
    closes = [b.close for b in bars]
    ma = lambda window: sum(closes[-window:]) / min(window, len(closes))
    signal, reason = 'HOLD', '未触发当前策略的开平仓条件'
    if strategy == 'BUY_AND_HOLD':
        if direction == 0 and first_entry:
            signal, reason = 'BUY', '买入持有基准首次建仓'
    elif strategy == 'MOMENTUM_BREAKOUT':
        upper, lower = max(b.high for b in bars[-21:-1]), min(b.low for b in bars[-21:-1])
        volume_ok = bar.volume > sum(b.volume for b in bars[-11:-1])/10 * 1.05
        if direction == 0 and volume_ok:
            if bar.close > upper and bar.close > ma(60): signal, reason = 'BUY', '放量突破前20日高点并顺MA60'
            elif bar.close < lower and bar.close < ma(60): signal, reason = 'SELL', '放量跌破前20日低点并顺MA60'
        elif direction > 0 and bar.close < ma(20): signal, reason = 'FLATTEN', '跌破MA20平多'
        elif direction < 0 and bar.close > ma(20): signal, reason = 'FLATTEN', '突破MA20平空'
    elif strategy == 'BOLLINGER_REVERSAL':
        mean = ma(15)
        std = math.sqrt(sum((v-mean)**2 for v in closes[-15:])/len(closes[-15:]))
        if direction == 0 and std > 0:
            if bar.close <= mean-2.2*std: signal, reason = 'BUY', '触及15日布林下轨，均值回归做多'
            elif bar.close >= mean+2.2*std: signal, reason = 'SELL', '触及15日布林上轨，均值回归做空'
        elif direction > 0 and bar.close >= mean: signal, reason = 'FLATTEN', '回归布林中轨平多'
        elif direction < 0 and bar.close <= mean: signal, reason = 'FLATTEN', '回归布林中轨平空'
    elif strategy == 'DUAL_THRUST':
        window = bars[-5:-1]
        width = max(max(b.high for b in window)-min(b.close for b in window),
                    max(b.close for b in window)-min(b.low for b in window))
        if direction == 0:
            if bar.close > bar.open+.5*width and bar.close > ma(60): signal, reason = 'BUY', '突破Dual Thrust上轨并顺MA60'
            elif bar.close < bar.open-.5*width and bar.close < ma(60): signal, reason = 'SELL', '跌破Dual Thrust下轨并顺MA60'
        elif direction > 0 and bar.close < ma(10): signal, reason = 'FLATTEN', '跌破MA10平多'
        elif direction < 0 and bar.close > ma(10): signal, reason = 'FLATTEN', '突破MA10平空'
    elif strategy == 'ADAPTIVE_CTA':
        ema = closes[0]
        for close in closes[1:]: ema = close*(2/21)+ema*(1-2/21)
        if direction == 0:
            if bar.close > ema+1.8*atr and bar.close > ma(60): signal, reason = 'BUY', '突破肯特纳上轨并顺MA60'
            elif bar.close < ema-1.8*atr and bar.close < ma(60): signal, reason = 'SELL', '跌破肯特纳下轨并顺MA60'
        elif direction > 0 and bar.close < ema: signal, reason = 'FLATTEN', '跌破EMA20平多'
        elif direction < 0 and bar.close > ema: signal, reason = 'FLATTEN', '突破EMA20平空'
    else:
        previous = bars[-2]
        quote = MarketQuote(symbol=symbol, name=symbol, price=bar.close, change=bar.close-previous.close,
            change_pct=(bar.close/previous.close-1)*100, open=bar.open, high=bar.high, low=bar.low,
            prev_close=previous.close, prev_settlement=previous.close, volume=bar.volume,
            turnover=bar.volume*bar.close*5, open_interest=bar.open_interest, timestamp=bar.timestamp)
        decision = (engine or HolisticFusionEngine()).evaluate_all(
            {'klines': list(bars), 'quote': quote, 'analysis_time': bar.timestamp})
        score, resonance = decision.composite_score, decision.directional_resonance
        if direction == 0 and resonance >= .65:
            if score >= 28 and bar.close > ma(60): signal, reason = 'BUY', f'十四维多头共振{score:.1f}分'
            elif score <= -28 and bar.close < ma(60): signal, reason = 'SELL', f'十四维空头共振{score:.1f}分'
        elif direction > 0 and (score < 0 or bar.close < ma(20)): signal, reason = 'FLATTEN', '多头共振减弱平多'
        elif direction < 0 and (score > 0 or bar.close > ma(20)): signal, reason = 'FLATTEN', '空头共振减弱平空'
    return DailySignal(signal, reason, atr, required)
