"""
AI-QUANT 预测引擎基类与标准预测结果结构
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, Optional

@dataclass
class PredictionResult:
    """单个维度的标准化预测输出结果"""
    dimension_name: str         # 维度中文名称 (如 "气象生态模拟模型")
    dimension_key: str          # 维度英文键名 (如 "weather")
    score: Optional[float]      # 不可用和文化参考维度不产生分数
    confidence: Optional[float]
    direction: str              # 多空方向: "BEARISH" / "BULLISH" / "NEUTRAL"
    summary: str                # 核心研判摘要
    recommendation: str         # 针对该维度的操作建议
    category: str = "EMPIRICAL"
    data_status: str = "FRESH"
    included_in_score: bool = True
    weight: float = 0.0
    source_name: str = ""
    source_url: str = ""
    observed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    sample_size: int = 0
    key_metrics: Dict[str, Any] = field(default_factory=dict)  # 核心量化指标
    details: Dict[str, Any] = field(default_factory=dict)      # 深度分析明细
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

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
        *,
        weight: float = 0.0,
        source_name: str = "",
        source_url: str = "",
        observed_at: Optional[datetime] = None,
        sample_size: int = 0,
        data_status: str = "FRESH",
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
            category="EMPIRICAL",
            data_status=data_status,
            included_in_score=True,
            weight=max(0.0, weight),
            source_name=source_name,
            source_url=source_url,
            observed_at=observed_at or datetime.now(timezone.utc),
            sample_size=max(0, sample_size),
            key_metrics=key_metrics or {},
            details=details or {},
            timestamp=datetime.now(timezone.utc),
        )

    @classmethod
    def unavailable(
        cls,
        dimension_name: str,
        dimension_key: str,
        source_name: str,
        source_url: str,
        reason: str,
    ) -> "PredictionResult":
        return cls(
            dimension_name=dimension_name,
            dimension_key=dimension_key,
            score=None,
            confidence=None,
            direction="UNAVAILABLE",
            summary=reason,
            recommendation="等待真实数据源恢复后重新计算。",
            category="EMPIRICAL",
            data_status="UNAVAILABLE",
            included_in_score=False,
            weight=0.0,
            source_name=source_name,
            source_url=source_url,
            sample_size=0,
        )

    @classmethod
    def reference(
        cls,
        dimension_name: str,
        dimension_key: str,
        summary: str,
        recommendation: str,
        observed_at: datetime,
        key_metrics: Optional[Dict[str, Any]] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> "PredictionResult":
        return cls(
            dimension_name=dimension_name,
            dimension_key=dimension_key,
            score=None,
            confidence=None,
            direction="REFERENCE",
            summary=summary,
            recommendation=recommendation,
            category="CULTURAL_REFERENCE",
            data_status="REFERENCE",
            included_in_score=False,
            weight=0.0,
            source_name="真实时间与中国传统历法计算",
            source_url="https://github.com/6tail/lunar-python",
            observed_at=observed_at,
            sample_size=1,
            key_metrics=key_metrics or {},
            details=details or {},
        )

class BaseEngine(ABC):
    """预测引擎通用抽象基类"""

    def __init__(self, name: str, key: str, source_name: str = "", source_url: str = ""):
        self.name = name
        self.key = key
        self.source_name = source_name
        self.source_url = source_url

    @abstractmethod
    def predict(self, context: Dict[str, Any]) -> PredictionResult:
        """执行预测并返回标准输出"""
        pass
