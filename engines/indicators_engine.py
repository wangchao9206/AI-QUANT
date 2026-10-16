"""Technical indicators calculated only from observed K-line bars."""

from math import sqrt
from statistics import mean
from typing import Any, Dict

from config.settings import settings

from .base import BaseEngine, PredictionResult
from .empirical_engines import _atr  # B3: shared ATR helper, avoid duplication


class TechnicalIndicatorsEngine(BaseEngine):
    def __init__(self):
        super().__init__(
            name="技术指标",
            key="indicators",
            source_name="新浪期货日K",
            source_url="https://finance.sina.com.cn/futures/",
        )

    def predict(self, context: Dict[str, Any]) -> PredictionResult:
        klines = context.get("klines", [])
        quote = context.get("quote")
        if quote is None or len(klines) < 20:
            raise ValueError("Technical indicator model requires a live quote and at least 20 observed bars")

        closes = [bar.close for bar in klines]
        ma5 = mean(closes[-5:])
        ma10 = mean(closes[-10:])
        ma20 = mean(closes[-20:])
        ma60 = mean(closes[-60:]) if len(closes) >= 60 else mean(closes)

        changes = [closes[index] - closes[index - 1] for index in range(1, len(closes))]
        recent_changes = changes[-14:]
        avg_gain = mean(max(change, 0.0) for change in recent_changes)
        avg_loss = mean(max(-change, 0.0) for change in recent_changes)
        rsi14 = 100.0 if avg_loss == 0 else 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)

        recent_9 = klines[-9:]
        lowest_9 = min(bar.low for bar in recent_9)
        highest_9 = max(bar.high for bar in recent_9)
        stochastic_k = 50.0 if highest_9 == lowest_9 else (closes[-1] - lowest_9) / (highest_9 - lowest_9) * 100.0

        variance = mean((close - ma20) ** 2 for close in closes[-20:])
        standard_deviation = sqrt(variance)
        upper_boll = ma20 + 2.0 * standard_deviation
        lower_boll = ma20 - 2.0 * standard_deviation

        # B3: use shared _atr() instead of duplicating the true-range loop
        atr14 = _atr(klines, window=14)

        trend_score = ((closes[-1] / ma20) - 1.0) * 500.0
        alignment_score = 20.0 if ma5 > ma10 > ma20 else -20.0 if ma5 < ma10 < ma20 else 0.0
        rsi_score = (rsi14 - 50.0) * 0.8
        score = max(-100.0, min(100.0, trend_score + alignment_score + rsi_score))
        support = min(bar.low for bar in klines[-20:])
        resistance = max(bar.high for bar in klines[-20:])
        confidence = min(0.95, 0.65 + min(len(klines), 60) / 200.0)

        arrangement = "多头排列（MA5 > MA10 > MA20）" if ma5 > ma10 > ma20 else "空头排列（MA5 < MA10 < MA20）" if ma5 < ma10 < ma20 else "均线交错粘合缠绕"
        boll_bandwidth = (upper_boll - lower_boll) / ma20 * 100.0 if ma20 else 0.0

        if ma5 > ma10 > ma20 and closes[-1] > ma5:
            tech_desc = "短中长周期筹码全部处于一致盈利锁仓状态，均线多头束向上发散，均线支撑强劲，且价格站稳各均线上方，属于高确定性的上升趋势推进浪"
            tech_rating = "多头强势共振"
        elif ma5 < ma10 < ma20 and closes[-1] < ma5:
            tech_desc = "均线呈现空头瀑布发散，上方层层套牢盘压顶，反弹屡屡受阻于 MA5/10 动态压制，下行惯性尚未衰竭"
            tech_rating = "空头破位下行"
        else:
            tech_desc = "短周期与中周期均线发生缠绕，均线系统无明显发散方向，市场处于方向选择与筹码换手蓄势期"
            tech_rating = "震荡蓄势整理"

        summary = (
            f"【数据实证与观测基准】基于真实 K 线高精测算多维经典技术拓扑：MA5({ma5:.1f})、MA10({ma10:.1f})、MA20({ma20:.1f})、MA60({ma60:.1f}) 呈现“{arrangement}”；RSI(14) 强弱动量读数为 {rsi14:.1f}（多空分界 50.0），布林带动态包络区间为 [{lower_boll:.1f} ~ {upper_boll:.1f}]（带宽 {boll_bandwidth:.1f}%），KD 随机指标 K 值为 {stochastic_k:.1f}，真实波幅 ATR(14) 为 {atr14:.1f} 点。\n"
            f"【传导机制与多空机理】技术指标体系从趋势均线成本、震荡动能与统计通道三大维度刻画全市场持筹者的心理博弈。{tech_desc}。当均线发散且 RSI 位于 55~70 的健康强势区时，趋势跟踪策略形成自强正反馈；布林带上下轨（{lower_boll:.1f} ~ {upper_boll:.1f}）则标定了价格偏离 20 日均值的二倍标准差界限，有效识别超买与超卖临界点。\n"
            f"【量化研判结论】多指标技术共振综合打分为 {score:+.1f} 分（权重 {settings.weights.indicators * 100:.0f}%），技术面综合评级为“{tech_rating}”。"
        )
        recommendation = (
            f"【实操交易要领】近 20 个交易日经实证检验的关键支撑位于 {support:.1f}，阻力位于 {resistance:.1f}。建议依托 MA10 或 MA20 回踩均线作为低吸观察点，结合 ATR(14)={atr14:.1f} 设定动态跟踪止盈。\n"
            f"【风控防守底线】若日线有效跌破 MA20 均线生命线（收盘价连续 2 日站不上 MA20），或跌破 20 日绝对支撑位 {support:.1f}，必须坚决止损，防范趋势彻底转向。"
        )

        return PredictionResult.create(
            dimension_name=self.name,
            dimension_key=self.key,
            score=score,
            confidence=confidence,
            summary=summary,
            recommendation=recommendation,
            weight=settings.weights.indicators,
            source_name=self.source_name,
            source_url=self.source_url,
            observed_at=klines[-1].timestamp,
            sample_size=len(klines),
            key_metrics={
                "MA5": f"{ma5:.1f}",
                "MA10": f"{ma10:.1f}",
                "MA20": f"{ma20:.1f}",
                "MA60/全样本均线": f"{ma60:.1f}",
                "均线形态": arrangement,
                "RSI(14)": f"{rsi14:.1f}",
                "随机指标K": f"{stochastic_k:.1f}",
                "布林带宽": f"{boll_bandwidth:.1f}%",
                "ATR(14)": f"{atr14:.1f}",
                "20日支撑": f"{support:.1f}",
                "20日阻力": f"{resistance:.1f}",
            },
            details={"计算依据": "真实日K的开高低收"},
        )
