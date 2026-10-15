"""
AI-QUANT 系统全局配置模块
"""
import math
import os
from dataclasses import dataclass, field
from typing import List


@dataclass
class MarketConfig:
    default_symbol: str = "IFM"
    default_exchange: str = "CFFEX"
    symbols: List[str] = field(default_factory=lambda: ["IFM", "RBM", "MM", "CJM", "SIM", "TM"])
    update_interval_sec: int = 5
    # 数据源配置
    eastmoney_push2_url: str = "https://push2.eastmoney.com/api/qt/stock/get"
    eastmoney_batch_url: str = "https://push2.eastmoney.com/api/qt/ulist.np/get"


@dataclass
class WeightsConfig:
    """11 empirical dimensions (91%) plus 3 cultural-reference dimensions (9%)."""
    weather: float = 0.11
    momentum: float = 0.13
    indicators: float = 0.11
    sentiment: float = 0.07
    supply_demand: float = 0.09
    policy: float = 0.07
    positioning: float = 0.08
    execution: float = 0.09
    spread: float = 0.06
    term_structure: float = 0.05
    liquidity: float = 0.05
    liuyao: float = 0.03
    iching: float = 0.03
    qimen: float = 0.03

    def __post_init__(self) -> None:
        total = sum(
            getattr(self, name)
            for name in (
                "weather", "momentum", "indicators", "sentiment", "supply_demand",
                "policy", "positioning", "execution", "spread", "term_structure",
                "liquidity", "liuyao", "iching", "qimen",
            )
        )
        assert math.isclose(total, 1.0, abs_tol=1e-6), (
            f"All scoring weights must sum to 1.0; got {total:.6f}"
        )


@dataclass
class RiskConfig:
    max_position_pct: float = 0.10     # 单品种最大持仓比例 10%
    atr_stop_multiplier: float = 2.0    # ATR 移动止损倍数
    hard_stop_loss_pct: float = 0.035  # 硬止损线 3.5%
    take_profit_rr_ratio: float = 2.5  # 最低盈亏比 2.5:1


@dataclass
class SystemSettings:
    app_name: str = "AI-QUANT"
    # The suffix is a trust marker consumed by strategy-service: predictions
    # without it are legacy/generated records and are never served as fallback.
    version: str = "2.1.0+observed.2"
    base_dir: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    reports_dir: str = os.path.join(base_dir, "reports")
    market: MarketConfig = field(default_factory=MarketConfig)
    weights: WeightsConfig = field(default_factory=WeightsConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)


settings = SystemSettings()
