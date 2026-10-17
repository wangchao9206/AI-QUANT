from datetime import date, datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


def to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class DataStatus(str, Enum):
    FRESH = "FRESH"
    CACHED = "CACHED"
    DEGRADED = "DEGRADED"


class DimensionDataStatus(str, Enum):
    FRESH = "FRESH"
    CACHED = "CACHED"
    UNAVAILABLE = "UNAVAILABLE"
    REFERENCE = "REFERENCE"


class HealthResponse(ApiModel):
    status: str
    service: str
    model_version: str


class ProviderStatusResponse(ApiModel):
    provider: str
    configured: bool
    connected: bool
    last_event_at: datetime | None = None
    fallback_active: bool
    message: str


class QuoteResponse(ApiModel):
    symbol: str
    display_name: str
    price: float
    change: float
    change_pct: float
    source: str
    data_status: DataStatus
    data_timestamp: datetime


class HistoryPointResponse(ApiModel):
    timestamp: datetime
    price: float
    change_pct: float
    open: float | None = None
    high: float | None = None
    low: float | None = None
    volume: int | None = None
    open_interest: int | None = None


class HistoryResponse(ApiModel):
    symbol: str
    series_symbol: str
    series_type: Literal["CONTINUOUS", "CONTRACT", "LIVE_SNAPSHOT"]
    source: str
    data_status: DataStatus
    data_timestamp: datetime
    points: list[HistoryPointResponse]


class TermStructurePointResponse(ApiModel):
    contract: str
    maturity_date: date
    price: float


class TermStructureResponse(ApiModel):
    root_symbol: str
    data_status: DataStatus
    data_timestamp: datetime
    contracts: list[TermStructurePointResponse]


class InstrumentResponse(ApiModel):
    exchange: str
    exchange_name: str
    name: str
    node: str
    root_symbol: str
    main_symbol: str
    contracts: list[str]


class InstrumentExchangeResponse(ApiModel):
    code: str
    name: str
    instruments: list[InstrumentResponse]


class InstrumentCatalogResponse(ApiModel):
    source: str
    data_status: DataStatus
    data_timestamp: datetime
    exchanges: list[InstrumentExchangeResponse]


class DimensionResponse(ApiModel):
    key: str
    name: str
    score: float | None = Field(default=None, ge=-100, le=100)
    direction: str
    confidence: float | None = Field(default=None, ge=0, le=1)
    summary: str
    recommendation: str
    category: str
    data_status: DimensionDataStatus
    included_in_score: bool
    weight: float = Field(ge=0, le=1)
    source_name: str
    source_url: str
    observed_at: datetime
    sample_size: int = Field(ge=0)
    key_metrics: dict[str, Any]


class PredictionResponse(ApiModel):
    symbol: str
    display_name: str
    price: float
    change: float
    change_pct: float
    composite_score: float = Field(ge=-100, le=100)
    resonance: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    signal: str
    action_directive: str
    recommended_position_pct: float
    target_price: float
    stop_loss_price: float
    data_status: DataStatus
    data_timestamp: datetime
    model_version: str
    trace_id: str
    dimensions: list[DimensionResponse]
    cultural_references: list[DimensionResponse] = Field(default_factory=list)
    event_windows: list[str]


class ErrorResponse(ApiModel):
    code: str
    message: str
    trace_id: str


class KeyEvidenceResponse(ApiModel):
    name: str
    score: float | None = None
    direction: str
    summary: str


class LeadAnalysisResponse(ApiModel):
    core_anomaly: str
    market_context: str
    news_driver: str
    key_evidence: list[KeyEvidenceResponse] = Field(default_factory=list)


class LeadExecutionResponse(ApiModel):
    action_directive: str
    entry_zone: str
    target_price: float
    stop_loss_price: float
    recommended_position_pct: float
    risk_reward_ratio: str
    invalidation_condition: str


class OpportunityLeadResponse(ApiModel):
    id: str
    symbol: str
    display_name: str
    exchange: str
    price: float
    change: float
    change_pct: float
    direction: str
    signal: str
    urgency: str
    composite_score: float
    confidence: float
    algorithm_type: str
    algorithm_name: str
    algorithm_badge: str
    analysis: LeadAnalysisResponse
    execution: LeadExecutionResponse
    discovered_at: datetime
    data_status: DataStatus = DataStatus.CACHED
    data_timestamp: datetime | None = None


class LeadsResponse(ApiModel):
    source: str
    data_status: DataStatus
    scanned_count: int
    leads_count: int
    data_timestamp: datetime
    leads: list[OpportunityLeadResponse]


class BacktestRequest(ApiModel):
    cost_multiplier: float = Field(default=1.0, ge=1, le=5)
    symbol: str = Field(default="CJ0", pattern=r"^[A-Za-z]{1,4}(?:0|M)$")
    strategy: Literal[
        "HOLISTIC_14D",
        "MOMENTUM_BREAKOUT",
        "BOLLINGER_REVERSAL",
        "DUAL_THRUST",
        "ADAPTIVE_CTA",
        "BUY_AND_HOLD",
    ] = "HOLISTIC_14D"
    start_date: date | None = None
    end_date: date | None = None
    initial_capital: float = Field(default=1000000.0, gt=0, le=1_000_000_000)
    position_pct: float = Field(default=30.0, gt=0, le=100)
    fee_rate: float = Field(default=0.0001, ge=0, le=0.02)
    slippage: float = Field(default=1.0, ge=0, le=10000)
    stop_loss_atr: float = Field(default=2.0, ge=0, le=20)
    take_profit_atr: float = Field(default=4.0, ge=0, le=50)
    leverage: float | None = Field(default=None, gt=0, le=10)
    margin_rate: float = Field(default=0.12, gt=0, le=1)
    include_roll_cost: bool = True

    @model_validator(mode="after")
    def validate_date_range(self):
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("startDate must be on or before endDate")
        return self


class DailyEquityPointModel(ApiModel):
    date: str
    equity: float
    benchmark_equity: float
    cash: float
    position_pct: float
    daily_return_pct: float
    drawdown_pct: float


class TradeLogModel(ApiModel):
    timestamp: str
    action: str
    price: float
    position_pct: float
    pnl: float
    return_pct: float
    reason: str
    hold_bars: int
    contract: str | None = None
    lots: int = 0
    fee: float = 0.0
    slippage_cost: float = 0.0
    from_contract: str | None = None
    to_contract: str | None = None
    old_price: float | None = None
    new_price: float | None = None
    price_gap: float | None = None


class BacktestResponse(ApiModel):
    cost_multiplier: float = 1.0
    strategy_name: str
    symbol: str
    data_source: str
    data_timestamp: datetime
    provider_symbol: str
    initial_capital: float
    final_equity: float
    effective_leverage: float = 1.0
    roll_trades: int = 0
    total_roll_yield_pct: float = 0.0
    roll_cost_total: float = 0.0
    roll_price_gap_total: float = 0.0
    roll_price_gap_pct: float = 0.0
    include_roll_cost: bool = True
    execution_model: str = "NEXT_BAR_OPEN"
    roll_model_status: str = "UNAVAILABLE"
    limitations: list[str] = Field(default_factory=list)
    total_return_pct: float
    annualized_return_pct: float
    benchmark_return_pct: float
    alpha_pct: float
    max_drawdown_pct: float
    max_drawdown_days: int
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    profit_loss_ratio: float
    avg_trade_pnl: float
    avg_hold_bars: float
    daily_equity: list[DailyEquityPointModel]
    trade_logs: list[TradeLogModel]
