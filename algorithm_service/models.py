from datetime import datetime
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


class HealthResponse(ApiModel):
    status: str
    service: str
    model_version: str


class DimensionResponse(ApiModel):
    key: str
    name: str
    score: float = Field(ge=-100, le=100)
    direction: str
    confidence: float = Field(ge=0, le=1)
    summary: str
    recommendation: str
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
    event_windows: list[str]


class ErrorResponse(ApiModel):
    code: str
    message: str
    trace_id: str
