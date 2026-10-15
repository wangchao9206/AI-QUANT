from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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


class HistoryResponse(ApiModel):
    symbol: str
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
