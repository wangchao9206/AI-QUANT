"""
AI-QUANT 十一维全息合成决策引擎 (Fusion Engine)
多维归一化加权、多空共振度计算、贝叶斯决策与最终交易指令生成
"""
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Any, Optional

from config.settings import settings
from .base import BaseEngine, PredictionResult
from .weather_engine import WeatherSimulationEngine
from .momentum_engine import MomentumOrderFlowEngine
from .indicators_engine import TechnicalIndicatorsEngine
from .sentiment_engine import SentimentNLPEngine
from .sociology_engine import SociologyConsumptionEngine
from .policy_engine import PolicyDeliveryRulesEngine
from .psychology_engine import BehavioralPsychologyEngine
from .execution_engine import PragmaticExecutionEngine
from .liuyao_engine import LiuYaoMetaphysicsEngine
from .iching_engine import IChingPhilosophyEngine
from .qimen_engine import QiMenDunJiaEngine

@dataclass
class FusionDecision:
    """十一维全息合成最终决策成果物"""
    symbol: str
    composite_score: float             # 加权综合得分 [-100.0, +100.0]
    directional_resonance: float       # 方向共振度 [0.0, 1.0] (如 11/11 一致则为 1.0)
    composite_confidence: float        # 加权综合置信度
    primary_signal: str                # 主导交易信号: STRONG_SELL / SELL / HOLD / BUY / STRONG_BUY
    action_directive: str              # 核心行动纲领
    recommended_position_pct: float    # 建议持仓比例 (负数为做空, 正数为做多)
    target_price_tp1: float            # 目标位 1
    target_price_tp2: float            # 目标位 2
    stop_loss_price: float             # 严守止损位
    key_event_windows: List[str]       # 关键时空观察窗口
    dimension_results: Dict[str, PredictionResult] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

class HolisticFusionEngine:
    """十一维全息决策合成总引擎"""

    def __init__(self):
        # 注册 11 个专业子引擎
        self.engines: List[BaseEngine] = [
            WeatherSimulationEngine(),       # 1. 气象生态模拟
            MomentumOrderFlowEngine(),       # 2. 动能与资金量价
            TechnicalIndicatorsEngine(),     # 3. 经典量化指标
            SentimentNLPEngine(),            # 4. 舆情情感量化
            SociologyConsumptionEngine(),    # 5. 社会学消费变迁
            PolicyDeliveryRulesEngine(),     # 6. 政策与仓单博弈
            BehavioralPsychologyEngine(),    # 7. 行为金融心理博弈
            PragmaticExecutionEngine(),      # 8. 知行合一交易策略
            LiuYaoMetaphysicsEngine(),        # 9. 八卦六爻纳甲模型
            IChingPhilosophyEngine(),        # 10. 易经大象变易哲学
            QiMenDunJiaEngine(),             # 11. 奇门遁甲时空量化
        ]

    def evaluate_all(self, context: Dict[str, Any]) -> FusionDecision:
        """运行所有 11 个引擎并执行加权共振聚类分析"""
        quote = context.get("quote")
        symbol = quote.symbol if quote else settings.market.default_symbol
        current_price = quote.price if quote else 6610.0

        results: Dict[str, PredictionResult] = {}
        for engine in self.engines:
            res = engine.predict(context)
            results[engine.key] = res

        # 获取权重配置
        weights = {
            "weather": settings.weights.weather,
            "momentum": settings.weights.momentum,
            "indicators": settings.weights.indicators,
            "sentiment": settings.weights.sentiment,
            "sociology": settings.weights.sociology,
            "policy": settings.weights.policy,
            "psychology": settings.weights.psychology,
            "execution": settings.weights.execution,
            "liuyao": settings.weights.liuyao,
            "iching": settings.weights.iching,
            "qimen": settings.weights.qimen,
        }

        # 归一化权重计算综合得分
        total_weight = sum(weights.values())
        composite_score = sum(
            (weights.get(k, 0.0) / total_weight) * res.score
            for k, res in results.items()
        )

        # 加权置信度
        composite_conf = sum(
            (weights.get(k, 0.0) / total_weight) * res.confidence
            for k, res in results.items()
        )

        # 计算方向共振度 (共振方向占比)
        bearish_count = sum(1 for res in results.values() if res.direction == "BEARISH")
        bullish_count = sum(1 for res in results.values() if res.direction == "BULLISH")
        total_count = len(results)
        directional_resonance = max(bearish_count, bullish_count) / total_count

        # 判定交易信号与动作指令
        if composite_score <= -60.0 and directional_resonance >= 0.8:
            primary_signal = "STRONG_SELL"
            action_directive = "顺势逢高沽空 / 空单坚定持有，严格防守止损"
            recommended_pos = -0.15  # 15% 净空头仓位
        elif composite_score <= -25.0:
            primary_signal = "SELL"
            action_directive = "反弹减仓 / 少量轻仓试空"
            recommended_pos = -0.08
        elif composite_score >= 60.0 and directional_resonance >= 0.8:
            primary_signal = "STRONG_BUY"
            action_directive = "右侧放量突破，积极做多"
            recommended_pos = 0.15
        elif composite_score >= 25.0:
            primary_signal = "BUY"
            action_directive = "震荡低吸 / 轻仓试多"
            recommended_pos = 0.08
        else:
            primary_signal = "HOLD"
            action_directive = "多空分歧中性，空仓观望"
            recommended_pos = 0.0

        # 风控价位推导
        tp1 = round(min(current_price - 110.0, 6500.0), 0)
        tp2 = 6300.0
        stop_loss = 6750.0

        event_windows = [
            "2026-10-13至10-20：动能加速下探期（考验6,500整数大关）",
            "2026-10-21至10-28：霜降新枣集中开秤期（奇门换局，现货锚定）",
            "2026-11-07前后：立冬周期拐点期（六爻水旺生木，冬储估值修复）"
        ]

        return FusionDecision(
            symbol=symbol,
            composite_score=round(composite_score, 1),
            directional_resonance=round(directional_resonance, 2),
            composite_confidence=round(composite_conf, 2),
            primary_signal=primary_signal,
            action_directive=action_directive,
            recommended_position_pct=recommended_pos,
            target_price_tp1=tp1,
            target_price_tp2=tp2,
            stop_loss_price=stop_loss,
            key_event_windows=event_windows,
            dimension_results=results,
            timestamp=datetime.now()
        )
