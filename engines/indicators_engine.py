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

        arrangement = "多头排列" if ma5 > ma10 > ma20 else "空头排列" if ma5 < ma10 < ma20 else "均线交错"
        summary = (
            f"真实 K 线计算结果：MA5={ma5:.1f}、MA10={ma10:.1f}、MA20={ma20:.1f}，"
            f"均线为{arrangement}；RSI(14)={rsi14:.1f}，布林区间 {lower_boll:.1f}–{upper_boll:.1f}，"
            f"ATR(14)={atr14:.1f}。"
        )
        recommendation = (
            f"近20日观测支撑 {support:.1f}、阻力 {resistance:.1f}；结合 ATR 设置风险边界，避免仅凭单一指标交易。"
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
                "RSI(14)": f"{rsi14:.1f}",
                "随机指标K": f"{stochastic_k:.1f}",
                "ATR(14)": f"{atr14:.1f}",
                "20日支撑": f"{support:.1f}",
                "20日阻力": f"{resistance:.1f}",
            },
            details={"计算依据": "真实日K的开高低收"},
        )
