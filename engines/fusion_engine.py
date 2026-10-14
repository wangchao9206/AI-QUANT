"""Fusion of observed market signals and explicitly labelled cultural references.

Eleven empirical dimensions carry 91% of the configured weight. Three deterministic
time-calendar references carry 3% each and remain serialized separately.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List

from config.settings import settings

from .base import BaseEngine, PredictionResult
from .empirical_engines import (
    CrossContractSpreadEngine,
    DeliveryPolicyEngine,
    ExecutionRiskEngine,
    LiquidityVolatilityEngine,
    NewsSentimentEngine,
    PositionCrowdingEngine,
    SupplyDemandPressureEngine,
    TermStructureEngine,
    WeatherPhenologyEngine,
    _atr,                       # B3: reuse shared ATR helper
)
from .indicators_engine import TechnicalIndicatorsEngine
from .momentum_engine import MomentumOrderFlowEngine
from .cultural_reference_engines import (
    IChingCulturalReferenceEngine,
    LiuYaoCulturalReferenceEngine,
    QiMenCulturalReferenceEngine,
)


@dataclass
class FusionDecision:
    symbol: str
    composite_score: float
    directional_resonance: float
    composite_confidence: float
    primary_signal: str
    action_directive: str
    recommended_position_pct: float
    target_price_tp1: float
    target_price_tp2: float
    stop_loss_price: float
    key_event_windows: List[str]
    dimension_results: Dict[str, PredictionResult] = field(default_factory=dict)
    cultural_references: Dict[str, PredictionResult] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class HolisticFusionEngine:
    """Fuse 11 empirical dimensions and 3 labelled cultural references."""

    def __init__(self):
        self.engines: List[BaseEngine] = [
            WeatherPhenologyEngine(),
            MomentumOrderFlowEngine(),
            TechnicalIndicatorsEngine(),
            NewsSentimentEngine(),
            SupplyDemandPressureEngine(),
            DeliveryPolicyEngine(),
            PositionCrowdingEngine(),
            ExecutionRiskEngine(),
            CrossContractSpreadEngine(),
            TermStructureEngine(),
            LiquidityVolatilityEngine(),
        ]
        self.cultural_engines: List[BaseEngine] = [
            LiuYaoCulturalReferenceEngine(),
            IChingCulturalReferenceEngine(),
            QiMenCulturalReferenceEngine(),
        ]

    def evaluate_all(self, context: Dict[str, Any]) -> FusionDecision:
        quote = context.get("quote")
        klines = context.get("klines", [])
        if quote is None or len(klines) < 20:
            raise ValueError("Live quote and at least 20 observed K-lines are required")

        # ── 1. 采集实证维度 ──────────────────────────────────────────
        results: Dict[str, PredictionResult] = {}
        for engine in self.engines:
            try:
                results[engine.key] = engine.predict(context)
            except Exception as exc:
                results[engine.key] = PredictionResult.unavailable(
                    engine.name, engine.key, engine.source_name, engine.source_url, str(exc),
                )

        # ── 2. 采集文化参考维度 ──────────────────────────────────────
        cultural_references: Dict[str, PredictionResult] = {}
        for engine in self.cultural_engines:
            try:
                cultural_references[engine.key] = engine.predict(context)
            except Exception as exc:
                cultural_references[engine.key] = PredictionResult.unavailable(
                    engine.name, engine.key, "", "", str(exc),
                )

        # Cultural references remain separately serialized but participate with
        # their configured small weights, matching the approved afternoon model.
        all_scored = {**results, **cultural_references}
        eligible = [
            r for r in all_scored.values()
            if r.included_in_score and r.score is not None and r.confidence is not None
        ]
        if len(eligible) < 2:
            raise ValueError("At least two scored dimensions are required")
        total_weight = sum(r.weight for r in eligible)
        if total_weight <= 0:
            raise ValueError("Eligible dimensions have no positive weight")

        composite_score = sum(r.weight * r.score for r in eligible) / total_weight
        composite_confidence = sum(r.weight * r.confidence for r in eligible) / total_weight

        bearish_count = sum(r.direction == "BEARISH" for r in eligible)
        bullish_count = sum(r.direction == "BULLISH" for r in eligible)
        directional_resonance = max(bearish_count, bullish_count) / len(eligible)

        # ── 4. 信号与仓位 ────────────────────────────────────────────
        if composite_score <= -55.0 and directional_resonance >= 0.8:
            signal = "STRONG_SELL"
            directive = "下行动量高度一致，严格按波动率边界控制空头风险"
        elif composite_score <= -25.0:
            signal = "SELL"
            directive = "量价偏弱，仅允许小仓位并设置硬止损"
        elif composite_score >= 55.0 and directional_resonance >= 0.8:
            signal = "STRONG_BUY"
            directive = "上行动量高度一致，严格按波动率边界控制多头风险"
        elif composite_score >= 25.0:
            signal = "BUY"
            directive = "量价偏强，仅允许小仓位并设置硬止损"
        else:
            signal = "HOLD"
            directive = "真实量价信号分歧，等待方向确认"

        # B6 fix: 仓位与评分线性正比，上限为 max_position_pct（替代5档硬编码）
        max_pos = settings.risk.max_position_pct
        position = round(
            max(-max_pos, min(max_pos, composite_score / 100.0 * max_pos)),
            3,
        )

        # ── 5. 止盈止损（B3 fix：使用共享 _atr()）──────────────────
        atr = _atr(klines, window=14)
        direction = -1.0 if composite_score < -10 else 1.0 if composite_score > 10 else 0.0
        target_price_tp1 = round(quote.price + direction * atr * 1.5, 1)
        target_price_tp2 = round(quote.price + direction * atr * 2.5, 1)
        stop_loss_price = round(quote.price - direction * atr, 1) if direction else round(quote.price, 1)

        return FusionDecision(
            symbol=quote.symbol,
            composite_score=round(composite_score, 1),
            directional_resonance=round(directional_resonance, 2),
            composite_confidence=round(composite_confidence, 2),
            primary_signal=signal,
            action_directive=directive,
            recommended_position_pct=position,
            target_price_tp1=target_price_tp1,
            target_price_tp2=target_price_tp2,
            stop_loss_price=stop_loss_price,
            key_event_windows=[
                "下一交易日：确认价格方向是否获得成交量配合",
                "未来5个交易日：观察MA5与MA10是否形成有效交叉",
                "触及20日高低区间：重新计算止盈与止损边界",
            ],
            dimension_results=results,
            cultural_references=cultural_references,
            timestamp=context.get("analysis_time") or datetime.now(timezone.utc),
        )
