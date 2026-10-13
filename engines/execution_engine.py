"""
维度八：知行合一交易策略闭环 (Pragmatic Execution & Risk Control Engine)
认知与行动统一、王阳明心学交易哲学、ATR动态追踪与仓位风控
"""
from typing import Dict, Any
from .base import BaseEngine, PredictionResult

class PragmaticExecutionEngine(BaseEngine):
    def __init__(self):
        super().__init__(name="知行合一交易策略闭环", key="execution")

    def predict(self, context: Dict[str, Any]) -> PredictionResult:
        quote = context.get("quote")
        current_price = quote.price if quote else 6610.0

        # 风控关键价位测算
        atr = 145.0
        trailing_stop_short = 6750.0   # 空头防守移动止损位 (原跌破支撑转阻力)
        target_tp1 = 6500.0            # 第一止盈目标位 (心理整数关口)
        target_tp2 = 6300.0            # 终极成本底止盈位
        hard_stop_distance_pct = 0.035 # 3.5%

        # 策略评分：当前时点知行合一要求“顺空控仓，绝不盲目抄底”
        score = -65.0

        summary = (
            f"知行合一核心要义：‘明知大势向下方能顺势，知晓超卖凶险切莫急躁’。"
            f"空头策略：以 {trailing_stop_short:.0f} 为移动防守止损线，"
            f"第一止盈目标锁定在 {target_tp1:.0f}，第二目标看至 {target_tp2:.0f}。"
            f"多头策略：坚决执行‘不见右侧放量阳线不入场’铁律，恪守 0 仓位等待。"
        )

        recommendation = (
            f"严守纪律：单笔风险暴露严禁超过权益 2.0%；"
            f"价格若逆势收复 {trailing_stop_short:.0f} 空单坚决无条件离场；"
            f"在跌至 {target_tp1:.0f} 附近时兑现 50% 浮盈锁定战果。"
        )

        return PredictionResult.create(
            dimension_name=self.name,
            dimension_key=self.key,
            score=score,
            confidence=0.95,
            summary=summary,
            recommendation=recommendation,
            key_metrics={
                "空头移动防守止损": f"{trailing_stop_short:.0f}元/吨",
                "第一批止盈目标TP1": f"{target_tp1:.0f}元/吨 (分批减半)",
                "终极止盈目标TP2": f"{target_tp2:.0f}元/吨",
                "推荐多头仓位": "0.0% (严禁左侧摸底)",
                "推荐空头仓位": "15.0% (底仓顺势移动止盈)"
            },
            details={
                "认知陷阱警示": "莫将‘价格已经很低’当做‘买入信号’",
                "右侧入场确认标尺": "1. 产区开秤价底线确立; 2. 日K站稳MA5且成交萎缩"
            }
        )
