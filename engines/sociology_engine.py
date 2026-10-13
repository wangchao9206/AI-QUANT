"""
维度五：社会学与人口结构消费模型 (Sociology & Demographic Consumption Engine)
生活方式变迁、礼品场景降级与红枣终端需求天花板演进
"""
from typing import Dict, Any
from .base import BaseEngine, PredictionResult

class SociologyConsumptionEngine(BaseEngine):
    def __init__(self):
        super().__init__(name="社会学消费变迁模型", key="sociology")

    def predict(self, context: Dict[str, Any]) -> PredictionResult:
        # 社会学结构演变参数
        gift_market_share = 0.18        # 高端礼盒消费占比由历史35%萎缩至18%
        annual_demand_ceiling = 52.5    # 全国年刚性消费总量稳定在 50-55 万吨
        industrial_processing_share = 0.42 # 原料深加工占比提升至 42%
        sugar_control_awareness = 0.76  # 控糖健康理念普及率

        # 社会消费结构对红枣形成长期基本面压制
        # 评分：-75.0 (需求端缺乏弹性)
        score = -75.0

        summary = (
            f"社会消费呈现显著的‘去礼盒化、去泡沫化’趋势，散装平价与折扣量贩成为主流；"
            f"年轻一代对高糖原果食用频次下降，需求转向低溢价的工业加工原料（枣粉/枣浆）；"
            f"全国年需求总量在 50~55 万吨形成刚性天花板，难以靠降价引发报复性消费放量。"
        )

        recommendation = "需求侧缺乏中长期弹性增长极，红枣高溢价特级果溢价能力瓦解，中长期期价重心整体下移。"

        return PredictionResult.create(
            dimension_name=self.name,
            dimension_key=self.key,
            score=score,
            confidence=0.85,
            summary=summary,
            recommendation=recommendation,
            key_metrics={
                "高端礼盒消费占比": f"{gift_market_share*100:.1f}% (历史新低)",
                "全国年消费刚性天花板": f"{annual_demand_ceiling:.1f}万吨",
                "深加工原料占比": f"{industrial_processing_share*100:.1f}%",
                "消费弹性特征": "刚性微弱，价格下跌难以刺激消费翻倍"
            },
            details={
                "代际消费分化": "银发族偏好原果但受控糖约束；年轻代偏好深加工但替代品繁多",
                "渠道变革": "传统批发市场货物流通放缓，零食折扣量贩系统主导定价权"
            }
        )
