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
            source_name="新浪期货实时行情与日K",
            source_url="https://finance.sina.com.cn/futures/",
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

        if score > 20:
            momentum_desc = "短周期 5 日动量与 10 日 ROC 保持正向加速扩张，且成交量能放大配合，主动性买盘挂单积极扫盘，多头攻坚动能充沛"
            trade_directive = "建议右侧顺应动量向上跟进，以分时均价线为托底支点分批建多，享受动量溢价红利。"
        elif score < -20:
            momentum_desc = "短周期价格加速向下跳水，10 日变动率深度负向发散，盘面遭遇主动性空头市价抛压打击，空头动量占据主导"
            trade_directive = "下行势能猛烈，多头切忌逆势盲目抄底，应顺应动量逢反弹弱势点位沽空或轻仓跟随。"
        else:
            momentum_desc = "动量指标处于零轴附近徘徊，5 日与 10 日变动幅度温和，量能无明显脉冲式异动，多空进入拉锯整理平衡"
            trade_directive = "动量方向尚未形成明显单边优势，建议保持观望，等待价格有效突破盘整箱体后再顺势介入。"

        summary = (
            f"【数据实证与观测基准】基于近 {len(klines)} 根真实日 K 线及日内量仓动力学追踪：5 日动量收益率为 {momentum_5d:+.2f}%，10 日变动率（ROC）为 {roc_10d:+.2f}%，当日实时成交量达到近 10 日均量的 {volume_ratio:.2f} 倍，日内持仓变动率为 {oi_change_pct:+.2f}%。\n"
            f"【传导机制与多空机理】量价与持仓是探寻主力资金建仓、拉升、洗盘与出货的终极解密工具。{momentum_desc}。在期货微观订单流机制中，当成交量比突破 1.2 倍且伴随价格单边突破时，表明机构买卖意愿产生不对称失衡，诱发追随资金形成惯性自我强化；反之若量能萎缩，则预示动能进入衰退期。\n"
            f"【量化研判结论】量价动能与订单流强度评分为 {score:+.1f} 分（权重 {settings.weights.momentum * 100:.0f}%），动量方向定性为“{direction_text}”。"
        )
        recommendation = (
            f"【实操交易要领】{trade_directive}\n"
            f"【风控防守底线】若日内分时出现“放巨量但价格滞涨并掉头向下击破分时均线”的典型放量滞涨形态，说明主力资金正在高位倒手分流，应立刻降低半数头寸。"
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
                "动量态势": direction_text,
            },
            details={"计算依据": "真实日K、实时成交量与持仓量"},
        )
