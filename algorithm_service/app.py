import logging
import os
import re
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Path, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

from config.settings import settings
from data.data_feed import KLineBar, MarketDataUnavailable, MarketQuote
from data.evidence_feed import EvidenceFeed, SHANGHAI_TZ
from data.live_feed import LiveMarketFeed
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
        self.market_feed = LiveMarketFeed()
        self.evidence_feed = EvidenceFeed(timeout=int(os.getenv("EVIDENCE_TIMEOUT", "3")))
        self.engine = HolisticFusionEngine()

    def predict(self, symbol: str, trace_id: str) -> dict[str, Any]:
        analysis_time = datetime.now(SHANGHAI_TZ)
        try:
            quote, klines, market_status = self.market_feed.prediction_inputs(symbol)
        except ValueError as exc:
            raise MarketDataUnavailable(str(exc)) from exc
        loaders = {
            "term_structure": lambda: self._term_structure_quotes(symbol),
            "weather": self.evidence_feed.get_weather,
            "news": self.evidence_feed.get_news,
            "trading_rules": self.evidence_feed.get_trading_rules,
        }
        collected: dict[str, Any] = {"quote": quote, "klines": klines}
        with ThreadPoolExecutor(max_workers=len(loaders), thread_name_prefix="evidence") as pool:
            futures = {pool.submit(loader): key for key, loader in loaders.items()}
            for future in as_completed(futures):
                key = futures[future]
                try:
                    collected[key] = future.result()
                except Exception as exc:
                    logger.warning("optional_evidence_unavailable", extra={"key": key, "error": str(exc), "trace_id": trace_id})

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
            "data_status": market_status,
            "data_timestamp": quote.timestamp.astimezone().isoformat(),
            "model_version": settings.version,
            "trace_id": trace_id,
            "dimensions": dimensions,
            "cultural_references": serialize_dimensions(decision.cultural_references),
            "event_windows": decision.key_event_windows,
        }

    def market_snapshot(self, symbol: str) -> dict[str, Any]:
        """Return the latest persisted observed-data snapshot without upstream I/O."""
        snapshot = self.market_feed.snapshot(symbol)
        if not snapshot["quote"] or not snapshot["history"]:
            raise MarketDataUnavailable(f"Observed market snapshot for {symbol} is still warming up")
        return snapshot

    def _term_structure_quotes(self, symbol: str) -> dict[str, MarketQuote]:
        snapshot = self.market_feed.term_snapshot(symbol)
        result: dict[str, MarketQuote] = {}
        for item in snapshot["contracts"]:
            observed_at = datetime.fromisoformat(item["dataTimestamp"])
            price = float(item["price"])
            code = item["contract"]
            result[code] = MarketQuote(
                symbol=code,
                name=code,
                price=price,
                change=0.0,
                change_pct=0.0,
                open=price,
                high=price,
                low=price,
                prev_close=price,
                prev_settlement=price,
                volume=0,
                turnover=0.0,
                open_interest=0,
                timestamp=observed_at,
                is_live=snapshot["dataStatus"] == "FRESH",
            )
        if not result:
            raise MarketDataUnavailable("No observed term structure is available")
        return result


prediction_service = PredictionService()


def normalize_symbol(symbol: str) -> str:
    normalized_symbol = symbol.upper().strip()
    if not SYMBOL_PATTERN.fullmatch(normalized_symbol):
        raise HTTPException(status_code=422, detail="Invalid futures symbol")
    return normalized_symbol


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("algorithm_service_started", extra={"model_version": settings.version})
    prediction_service.market_feed.start()
    try:
        yield
    finally:
        prediction_service.market_feed.stop()


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
        snapshot = await run_in_threadpool(prediction_service.market_feed.snapshot, normalized_symbol)
        item = snapshot["quote"]
        if not item:
            raise MarketDataUnavailable(f"No observed quote for {normalized_symbol}")
        return QuoteResponse(
            symbol=normalized_symbol,
            display_name=item["displayName"],
            price=item["price"],
            change=item["change"],
            change_pct=item["changePct"],
            source=item["source"],
            data_status=item["dataStatus"],
            data_timestamp=item["dataTimestamp"],
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
        snapshot = await run_in_threadpool(prediction_service.market_feed.snapshot, normalized_symbol)
        bars = snapshot["history"][-safe_limit:]
        if not bars:
            raise MarketDataUnavailable(f"No observed history for {normalized_symbol}")
        points = [
            {"timestamp": bar["timestamp"], "price": bar["price"], "change_pct": bar["changePct"]}
            for bar in bars
        ]
        return HistoryResponse(
            symbol=normalized_symbol,
            data_status="DEGRADED" if snapshot["quote"] and snapshot["quote"]["dataStatus"] == "DEGRADED" else "CACHED",
            data_timestamp=bars[-1]["timestamp"],
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
        snapshot = await run_in_threadpool(prediction_service.market_feed.term_snapshot, normalized_root)
        if not snapshot["contracts"] or not snapshot["dataTimestamp"]:
            raise MarketDataUnavailable("No trusted term structure contracts available")
        return TermStructureResponse(
            root_symbol=snapshot["rootSymbol"],
            data_status=snapshot["dataStatus"],
            data_timestamp=snapshot["dataTimestamp"],
            contracts=[
                {"contract": item["contract"], "maturity_date": item["maturityDate"], "price": item["price"]}
                for item in snapshot["contracts"]
            ],
        )
    except MarketDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
