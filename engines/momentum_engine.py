"""Price momentum, volume, and open-interest model using observed market data only."""

from statistics import mean
from typing import Any, Dict

from config.settings import settings

from .base import BaseEngine, PredictionResult


class MomentumOrderFlowEngine(BaseEngine):
    def __init__(self):
        super().__init__(
            name="量价动能",
            key="momentum",
            source_name="东方财富实时行情 + 新浪期货日K",
            source_url="https://quote.eastmoney.com/qihuo/CJM.html",
        )

    def predict(self, context: Dict[str, Any]) -> PredictionResult:
        quote = context.get("quote")
        klines = context.get("klines", [])
        if quote is None or len(klines) < 10:
            raise ValueError("Momentum model requires a live quote and at least 10 observed bars")

        closes = [bar.close for bar in klines]
        volumes = [bar.volume for bar in klines]
        interests = [bar.open_interest for bar in klines]
        price = quote.price
        momentum_5d = (price / closes[-6] - 1.0) * 100.0
        roc_10d = (price / closes[-11] - 1.0) * 100.0 if len(closes) >= 11 else momentum_5d
        average_volume = mean(volumes[-11:-1]) if len(volumes) >= 11 else mean(volumes[:-1])
        volume_ratio = quote.volume / average_volume if average_volume > 0 else 1.0
        previous_oi = next((value for value in reversed(interests[:-1]) if value > 0), 0)
        oi_change_pct = (
            (quote.open_interest / previous_oi - 1.0) * 100.0
            if previous_oi > 0 and quote.open_interest > 0
            else 0.0
        )

        score = max(-100.0, min(100.0, momentum_5d * 5.0 + roc_10d * 2.5))
        if volume_ratio > 1.2:
            score *= 1.1
        score = max(-100.0, min(100.0, score))
        direction_text = "上行动量" if score > 10 else "下行动量" if score < -10 else "震荡"
        confidence = min(0.95, 0.62 + min(len(klines), 60) / 200.0)

        summary = (
            f"基于 {len(klines)} 根真实日 K 计算：5 日动量 {momentum_5d:.2f}%，"
            f"10 日变动 {roc_10d:.2f}%，当日成交量为近 10 日均量的 {volume_ratio:.2f} 倍，"
            f"持仓较上一观测日变化 {oi_change_pct:.2f}%，当前判定为{direction_text}。"
        )
        recommendation = (
            "仅在成交量与持仓量同步确认时跟随当前方向，并用技术波动率设置止损。"
            if abs(score) >= 25
            else "量价方向尚未形成明显优势，等待突破后再评估。"
        )

        return PredictionResult.create(
            dimension_name=self.name,
            dimension_key=self.key,
            score=score,
            confidence=confidence,
            summary=summary,
            recommendation=recommendation,
            weight=settings.weights.momentum,
            source_name=self.source_name,
            source_url=self.source_url,
            observed_at=quote.timestamp,
            sample_size=len(klines),
            key_metrics={
                "最新价格": f"{price:.1f}",
                "日涨跌幅": f"{quote.change_pct:.2f}%",
                "5日动量": f"{momentum_5d:.2f}%",
                "10日变动率": f"{roc_10d:.2f}%",
                "成交量比": f"{volume_ratio:.2f}x",
                "持仓变化": f"{oi_change_pct:.2f}%",
            },
            details={"计算依据": "真实日K、实时成交量与持仓量"},
        )
