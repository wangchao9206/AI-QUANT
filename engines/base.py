"""
AI-QUANT 预测引擎基类与标准预测结果结构
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, Optional

@dataclass
class PredictionResult:
    """单个维度的标准化预测输出结果"""
    dimension_name: str         # 维度中文名称 (如 "气象生态模拟模型")
    dimension_key: str          # 维度英文键名 (如 "weather")
    score: float                # 预测评分 [-100.0 到 +100.0]，-100为极度看空，+100为极度看多，0为中性
    confidence: float           # 置信度 [0.0 到 1.0]
    direction: str              # 多空方向: "BEARISH" / "BULLISH" / "NEUTRAL"
    summary: str                # 核心研判摘要
    recommendation: str         # 针对该维度的操作建议
    key_metrics: Dict[str, Any] = field(default_factory=dict)  # 核心量化指标
    details: Dict[str, Any] = field(default_factory=dict)      # 深度分析明细
    timestamp: datetime = field(default_factory=datetime.now)

    @classmethod
    def create(
        cls,
        dimension_name: str,
        dimension_key: str,
        score: float,
        confidence: float,
        summary: str,
        recommendation: str,
        key_metrics: Optional[Dict[str, Any]] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> "PredictionResult":
        # 自动判定多空方向
        if score <= -20.0:
            direction = "BEARISH"
        elif score >= 20.0:
            direction = "BULLISH"
        else:
            direction = "NEUTRAL"

        return cls(
            dimension_name=dimension_name,
            dimension_key=dimension_key,
            score=max(-100.0, min(100.0, score)),
            confidence=max(0.0, min(1.0, confidence)),
            direction=direction,
            summary=summary,
            recommendation=recommendation,
            key_metrics=key_metrics or {},
            details=details or {},
            timestamp=datetime.now()
        )

class BaseEngine(ABC):
    """预测引擎通用抽象基类"""

    def __init__(self, name: str, key: str):
        self.name = name
        self.key = key

    @abstractmethod
    def predict(self, context: Dict[str, Any]) -> PredictionResult:
        """执行预测并返回标准输出"""
        pass
