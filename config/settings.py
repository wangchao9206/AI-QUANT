"""
AI-QUANT 系统全局配置模块
"""
import os
from dataclasses import dataclass, field
from typing import Dict, List

@dataclass
class MarketConfig:
    default_symbol: str = "CJ2701"
    default_exchange: str = "CZCE"
    symbols: List[str] = field(default_factory=lambda: ["CJ2701", "CJM", "CJ612", "CJ703", "CJ705", "AP501", "CF501"])
    update_interval_sec: int = 5
    # 数据源配置
    eastmoney_push2_url: str = "https://push2.eastmoney.com/api/qt/stock/get"
    eastmoney_batch_url: str = "https://push2.eastmoney.com/api/qt/ulist.np/get"

@dataclass
class WeightsConfig:
    """十一维全息预测模型初始权重分配 (AHP / 专家打分初值，后续可自适应调整)"""
    weather: float = 0.12        # 1. 气象生态模拟 (农产品核心供给)
    momentum: float = 0.14       # 2. 动能与资金量价 (短期趋势动力)
    indicators: float = 0.12     # 3. 经典量化指标 (超买超卖与均线)
    sentiment: float = 0.08      # 4. 舆情情感指数 (市场情绪共识)
    sociology: float = 0.08      # 5. 社会学消费变迁 (长期需求天花板)
    policy: float = 0.10         # 6. 政策与仓单交割 (规则红利与底线)
    psychology: float = 0.10     # 7. 行为金融心理博弈 (农户与贸易商心理)
    execution: float = 0.10      # 8. 知行合一交易风控 (盈亏比与纪律)
    liuyao: float = 0.06         # 9. 八卦六爻纳甲模型 (微观用神生克)
    iching: float = 0.05         # 10. 易经大象变易哲学 (宏观阴阳消长)
    qimen: float = 0.05          # 11. 奇门遁甲时空量化 (天时地利人和)

@dataclass
class RiskConfig:
    max_position_pct: float = 0.15     # 单品种最大持仓比例 15%
    atr_stop_multiplier: float = 2.0    # ATR 移动止损倍数
    hard_stop_loss_pct: float = 0.035  # 硬止损线 3.5%
    take_profit_rr_ratio: float = 2.5  # 最低盈亏比 2.5:1

@dataclass
class SystemSettings:
    app_name: str = "AI-QUANT"
    version: str = "1.0.0"
    base_dir: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    reports_dir: str = os.path.join(base_dir, "reports")
    market: MarketConfig = field(default_factory=MarketConfig)
    weights: WeightsConfig = field(default_factory=WeightsConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)

settings = SystemSettings()
