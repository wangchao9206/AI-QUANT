import logging
import os
import re
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Path, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

from config.settings import settings
from data.data_feed import FuturesDataFeed, KLineBar, MarketDataUnavailable
from data.evidence_feed import EvidenceFeed, SHANGHAI_TZ
from engines.fusion_engine import HolisticFusionEngine

from .models import (
    HealthResponse,
    HistoryResponse,
    PredictionResponse,
    QuoteResponse,
    TermStructureResponse,
)


logger = logging.getLogger("AI-QUANT.AlgorithmAPI")
SYMBOL_PATTERN = re.compile(r"^[A-Z]{1,4}[A-Z0-9]{0,8}$")


class PredictionService:
    def __init__(self) -> None:
        self.data_feed = FuturesDataFeed(timeout=int(os.getenv("MARKET_DATA_TIMEOUT", "3")))
        self.evidence_feed = EvidenceFeed(timeout=int(os.getenv("EVIDENCE_TIMEOUT", "3")))
        self.engine = HolisticFusionEngine()

    def predict(self, symbol: str, trace_id: str) -> dict[str, Any]:
        analysis_time = datetime.now(SHANGHAI_TZ)
        loaders = {
            "quote": lambda: self.data_feed.get_realtime_quote(symbol),
            "klines": lambda: self.data_feed.get_historical_klines(symbol, days=45),
            "term_structure": self.data_feed.get_term_structure,
            "weather": self.evidence_feed.get_weather,
            "news": self.evidence_feed.get_news,
            "trading_rules": self.evidence_feed.get_trading_rules,
        }
        collected: dict[str, Any] = {}
        with ThreadPoolExecutor(max_workers=len(loaders), thread_name_prefix="evidence") as pool:
            futures = {pool.submit(loader): key for key, loader in loaders.items()}
            for future in as_completed(futures):
                key = futures[future]
                try:
                    collected[key] = future.result()
                except Exception as exc:
                    if key in {"quote", "klines"}:
                        raise
                    logger.warning("optional_evidence_unavailable", extra={"key": key, "error": str(exc), "trace_id": trace_id})

        quote = collected["quote"]
        klines = collected["klines"]
        live_bar = KLineBar(
            timestamp=quote.timestamp,
            open=quote.open,
            high=quote.high,
            low=quote.low,
            close=quote.price,
            volume=quote.volume,
            open_interest=quote.open_interest,
        )
        if klines and klines[-1].timestamp.date() == quote.timestamp.date():
            # Same trading day: replace the last bar with fresh real-time data
            klines[-1] = live_bar
        elif live_bar.volume > 0:
            # Different day AND market is actually trading: append new bar
            # Guard prevents stale zero-volume bars (holidays, after-hours) from
            # polluting the kline series.
            klines.append(live_bar)
        collected.update({"symbol": symbol, "quote": quote, "klines": klines, "analysis_time": analysis_time})
        decision = self.engine.evaluate_all(collected)

        def serialize_dimensions(items):
            return [
            {
                "key": key,
                "name": value.dimension_name,
                "score": value.score,
                "direction": value.direction,
                "confidence": value.confidence,
                "summary": value.summary,
                "recommendation": value.recommendation,
                "category": value.category,
                "data_status": value.data_status,
                "included_in_score": value.included_in_score,
                "weight": value.weight,
                "source_name": value.source_name,
                "source_url": value.source_url,
                "observed_at": value.observed_at,
                "sample_size": value.sample_size,
                "key_metrics": value.key_metrics,
            }
            for key, value in items.items()
            ]

        dimensions = serialize_dimensions(decision.dimension_results)
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
            "cultural_references": serialize_dimensions(decision.cultural_references),
            "event_windows": decision.key_event_windows,
        }

    def market_snapshot(self, symbol: str) -> dict[str, Any]:
        """Return one coherent observed-data snapshot for background ingestion."""
        with ThreadPoolExecutor(max_workers=3, thread_name_prefix="market-snapshot") as pool:
            quote_future = pool.submit(self.data_feed.get_realtime_quote, symbol)
            history_future = pool.submit(self.data_feed.get_historical_klines, symbol, 240)
            term_future = pool.submit(self.data_feed.get_term_structure)
            quote = quote_future.result()
            history = history_future.result()
            curve = term_future.result()

        previous_close: float | None = None
        history_payload = []
        for bar in history:
            change = 0.0 if previous_close is None else bar.close - previous_close
            change_pct = 0.0 if not previous_close else change / previous_close * 100.0
            history_payload.append(
                {
                    "timestamp": bar.timestamp,
                    "price": bar.close,
                    "change": change,
                    "changePct": change_pct,
                }
            )
            previous_close = bar.close

        contracts = [
            {
                "contract": code,
                "maturityDate": contract_month(code),
                "price": item.price,
                "dataTimestamp": item.timestamp,
            }
            for code, item in curve.items()
            if code not in {"CJM", "CJ0"}
        ]
        return {
            "quote": {
                "symbol": symbol,
                "displayName": quote.name,
                "price": quote.price,
                "change": quote.change,
                "changePct": quote.change_pct,
                "source": "东方财富实时行情",
                "dataStatus": "FRESH" if quote.is_live else "CACHED",
                "dataTimestamp": quote.timestamp,
            },
            "history": history_payload,
            "contracts": contracts,
        }


prediction_service = PredictionService()


def normalize_symbol(symbol: str) -> str:
    normalized_symbol = symbol.upper().strip()
    if not SYMBOL_PATTERN.fullmatch(normalized_symbol):
        raise HTTPException(status_code=422, detail="Invalid futures symbol")
    return normalized_symbol


def contract_month(code: str) -> date:
    match = re.fullmatch(r"[A-Z]{1,4}(\d{3,4})", code)
    if not match:
        raise ValueError(f"Unsupported futures contract code: {code}")
    digits = match.group(1)
    if len(digits) == 4:
        year, month = 2000 + int(digits[:2]), int(digits[2:])
    else:
        current_year = datetime.now(timezone.utc).year
        year = (current_year // 10) * 10 + int(digits[0])
        if year < current_year - 1:
            year += 10
        month = int(digits[1:])
    return date(year, month, 1)


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


@app.get("/api/v1/market/{symbol}/snapshot")
async def market_snapshot(symbol: str = Path(min_length=2, max_length=12)) -> dict[str, Any]:
    normalized_symbol = normalize_symbol(symbol)
    try:
        return await run_in_threadpool(prediction_service.market_snapshot, normalized_symbol)
    except MarketDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/v1/predictions/{symbol}", response_model=PredictionResponse)
async def predict(
    request: Request,
    symbol: str = Path(min_length=2, max_length=12),
    x_trace_id: str | None = Header(default=None),
) -> PredictionResponse:
    normalized_symbol = normalize_symbol(symbol)

    trace_id = (x_trace_id or request.state.trace_id)[:128]
    try:
        result = await run_in_threadpool(prediction_service.predict, normalized_symbol, trace_id)
        return PredictionResponse.model_validate(result)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("prediction_failed", extra={"symbol": normalized_symbol, "trace_id": trace_id})
        raise HTTPException(status_code=503, detail="Prediction service temporarily unavailable") from exc


@app.get("/api/v1/market/{symbol}/quote", response_model=QuoteResponse)
async def quote(symbol: str = Path(min_length=2, max_length=12)) -> QuoteResponse:
    normalized_symbol = normalize_symbol(symbol)
    try:
        item = await run_in_threadpool(prediction_service.data_feed.get_realtime_quote, normalized_symbol)
        return QuoteResponse(
            symbol=normalized_symbol,
            display_name=item.name,
            price=item.price,
            change=item.change,
            change_pct=item.change_pct,
            source="东方财富实时行情",
            data_status="FRESH",
            data_timestamp=item.timestamp,
        )
    except MarketDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/v1/market/{symbol}/history", response_model=HistoryResponse)
async def history(
    symbol: str = Path(min_length=2, max_length=12),
    limit: int = 240,
) -> HistoryResponse:
    normalized_symbol = normalize_symbol(symbol)
    safe_limit = min(max(limit, 1), 1000)
    try:
        bars = await run_in_threadpool(
            prediction_service.data_feed.get_historical_klines,
            normalized_symbol,
            safe_limit,
        )
        points = []
        previous_close: float | None = None
        for bar in bars:
            change_pct = 0.0 if not previous_close else (bar.close - previous_close) / previous_close * 100.0
            points.append({"timestamp": bar.timestamp, "price": bar.close, "change_pct": change_pct})
            previous_close = bar.close
        return HistoryResponse(
            symbol=normalized_symbol,
            data_status="CACHED",
            data_timestamp=bars[-1].timestamp,
            points=points,
        )
    except MarketDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/v1/market/{root_symbol}/term-structure", response_model=TermStructureResponse)
async def term_structure(root_symbol: str = Path(min_length=2, max_length=12)) -> TermStructureResponse:
    normalized_root = normalize_symbol(root_symbol)
    if normalized_root not in {"CJ", "CJM", "CJ0"}:
        raise HTTPException(status_code=422, detail="Term structure is currently available for CJ only")
    try:
        curve = await run_in_threadpool(prediction_service.data_feed.get_term_structure)
        contracts = [
            {
                "contract": code,
                "maturity_date": contract_month(code),
                "price": item.price,
            }
            for code, item in curve.items()
            if code not in {"CJM", "CJ0"}
        ]
        if not contracts:
            raise MarketDataUnavailable("No trusted term structure contracts available")
        observed_at = max(item.timestamp for item in curve.values())
        return TermStructureResponse(
            root_symbol="CJ",
            data_status="FRESH",
            data_timestamp=observed_at,
            contracts=contracts,
        )
    except MarketDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
