import logging
import os
import re
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Path, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

from config.settings import settings
from data.data_feed import FuturesDataFeed
from engines.fusion_engine import HolisticFusionEngine

from .models import HealthResponse, PredictionResponse


logger = logging.getLogger("AI-QUANT.AlgorithmAPI")
SYMBOL_PATTERN = re.compile(r"^[A-Z]{1,4}[A-Z0-9]{0,8}$")


class PredictionService:
    def __init__(self) -> None:
        self.data_feed = FuturesDataFeed(timeout=int(os.getenv("MARKET_DATA_TIMEOUT", "3")))
        self.engine = HolisticFusionEngine()

    def predict(self, symbol: str, trace_id: str) -> dict[str, Any]:
        quote = self.data_feed.get_realtime_quote(symbol)
        klines = self.data_feed.get_historical_klines(symbol, days=45)
        decision = self.engine.evaluate_all(
            {"symbol": symbol, "quote": quote, "klines": klines}
        )
        dimensions = [
            {
                "key": key,
                "name": value.dimension_name,
                "score": value.score,
                "direction": value.direction,
                "confidence": value.confidence,
                "summary": value.summary,
                "recommendation": value.recommendation,
                "key_metrics": value.key_metrics,
            }
            for key, value in decision.dimension_results.items()
        ]
        return {
            "symbol": decision.symbol,
            "display_name": quote.name,
            "price": quote.price,
            "change": quote.change,
            "change_pct": quote.change_pct,
            "composite_score": decision.composite_score,
            "resonance": decision.directional_resonance,
            "confidence": decision.composite_confidence,
            "signal": decision.primary_signal,
            "action_directive": decision.action_directive,
            "recommended_position_pct": decision.recommended_position_pct,
            "target_price": decision.target_price_tp1,
            "stop_loss_price": decision.stop_loss_price,
            "data_status": "FRESH" if quote.is_live else "CACHED",
            "data_timestamp": quote.timestamp.astimezone().isoformat(),
            "model_version": settings.version,
            "trace_id": trace_id,
            "dimensions": dimensions,
            "event_windows": decision.key_event_windows,
        }


prediction_service = PredictionService()


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("algorithm_service_started", extra={"model_version": settings.version})
    yield


app = FastAPI(
    title="AI-QUANT Algorithm Service",
    version=settings.version,
    docs_url="/docs" if os.getenv("ENABLE_API_DOCS", "true").lower() == "true" else None,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")],
    allow_methods=["GET"],
    allow_headers=["X-Trace-Id", "Content-Type"],
    expose_headers=["X-Trace-Id"],
)


@app.middleware("http")
async def trace_id_middleware(request: Request, call_next):
    trace_id = request.headers.get("X-Trace-Id") or uuid.uuid4().hex
    request.state.trace_id = trace_id[:128]
    response = await call_next(request)
    response.headers["X-Trace-Id"] = request.state.trace_id
    return response


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="UP", service="algorithm-service", model_version=settings.version)


@app.get("/api/v1/predictions/{symbol}", response_model=PredictionResponse)
async def predict(
    request: Request,
    symbol: str = Path(min_length=2, max_length=12),
    x_trace_id: str | None = Header(default=None),
) -> PredictionResponse:
    normalized_symbol = symbol.upper().strip()
    if not SYMBOL_PATTERN.fullmatch(normalized_symbol):
        raise HTTPException(status_code=422, detail="Invalid futures symbol")

    trace_id = (x_trace_id or request.state.trace_id)[:128]
    try:
        result = await run_in_threadpool(prediction_service.predict, normalized_symbol, trace_id)
        return PredictionResponse.model_validate(result)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("prediction_failed", extra={"symbol": normalized_symbol, "trace_id": trace_id})
        raise HTTPException(status_code=503, detail="Prediction service temporarily unavailable") from exc
