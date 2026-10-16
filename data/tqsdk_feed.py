"""Authenticated TqSdk real-time feed with an explicitly degraded public fallback.

Only the worker thread in :class:`TqSdkRealtimeFeed` owns the TqApi instance.
HTTP request threads read immutable copies of the latest in-memory snapshots.
"""
from __future__ import annotations

import asyncio
import copy
import logging
import math
import os
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable

from data.data_feed import KLineBar, MarketQuote
from data.live_feed import EXCHANGES, LiveMarketFeed, SHANGHAI, SYMBOL, contract_maturity, root_symbol

logger = logging.getLogger("AI-QUANT.TqSdkFeed")

TQ_SOURCE = "天勤 TqSdk 实时行情"
FALLBACK_SUFFIX = "（TqSdk 实盘通道不可用，公开源降级）"
TQ_SYMBOL = re.compile(r"^(?P<exchange>[A-Z]+)\.(?P<instrument>[A-Za-z]+\d+)$")
TQ_MAIN_SYMBOL = re.compile(r"^KQ\.m@(?P<exchange>[A-Z]+)\.(?P<product>[A-Za-z]+)$")
TQ_EXCHANGE_NAMES = {
    "SHFE": "上海期货交易所（含上海国际能源交易中心）",
    "INE": "上海期货交易所（含上海国际能源交易中心）",
    "DCE": "大连商品交易所",
    "CZCE": "郑州商品交易所",
    "CFFEX": "中国金融期货交易所",
    "GFEX": "广州期货交易所",
}


def canonical_symbol(provider_symbol: str) -> str:
    """Convert a TqSdk instrument id to the canonical symbols used by the API."""
    value = provider_symbol.strip()
    main = TQ_MAIN_SYMBOL.fullmatch(value)
    if main:
        return f"{main.group('product').upper()}M"
    contract = TQ_SYMBOL.fullmatch(value)
    if contract:
        return contract.group("instrument").upper()
    raise ValueError(f"Unsupported TqSdk symbol: {provider_symbol}")


def provider_product(provider_symbol: str) -> tuple[str, str]:
    """Return exchange and upper-case product root for a TqSdk symbol."""
    main = TQ_MAIN_SYMBOL.fullmatch(provider_symbol.strip())
    if main:
        return main.group("exchange"), main.group("product").upper()
    contract = TQ_SYMBOL.fullmatch(provider_symbol.strip())
    if not contract:
        raise ValueError(f"Unsupported TqSdk symbol: {provider_symbol}")
    root = re.match(r"[A-Za-z]+", contract.group("instrument"))
    if not root:
        raise ValueError(f"Unsupported TqSdk symbol: {provider_symbol}")
    return contract.group("exchange"), root.group(0).upper()


def _value(item: Any, name: str, default: Any = None) -> Any:
    return item.get(name, default) if isinstance(item, dict) else getattr(item, name, default)


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def _observed_at(value: Any, now: datetime | None = None) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=value.tzinfo or SHANGHAI).astimezone(SHANGHAI)
    if isinstance(value, (int, float)) and math.isfinite(value):
        seconds = value / 1_000_000_000 if value > 10_000_000_000 else value
        return datetime.fromtimestamp(seconds, SHANGHAI)
    if isinstance(value, str) and value.strip():
        candidate = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(candidate)
            return parsed.replace(tzinfo=parsed.tzinfo or SHANGHAI).astimezone(SHANGHAI)
        except ValueError:
            pass
    return (now or datetime.now(SHANGHAI)).astimezone(SHANGHAI)


def _latest_timestamp(*values: str | None) -> str | None:
    observed: list[datetime] = []
    for value in values:
        if not value:
            continue
        try:
            parsed = datetime.fromisoformat(value)
            observed.append(parsed.replace(tzinfo=parsed.tzinfo or SHANGHAI))
        except ValueError:
            continue
    return max(observed).isoformat() if observed else None


def quote_to_snapshot(symbol: str, quote: Any, now: datetime | None = None) -> dict[str, Any]:
    """Convert a TqSdk Quote entity to the immutable API snapshot shape."""
    price = _finite(_value(quote, "last_price"))
    if price <= 0:
        raise ValueError("TqSdk quote has no positive last price")
    settlement = _finite(_value(quote, "pre_settlement"))
    previous_close = _finite(_value(quote, "pre_close"))
    baseline = settlement if settlement > 0 else previous_close
    if baseline <= 0:
        baseline = price
    observed = _observed_at(_value(quote, "datetime"), now)
    return {
        "symbol": symbol,
        "displayName": str(_value(quote, "instrument_name", symbol) or symbol),
        "price": price,
        "change": round(price - baseline, 6),
        "changePct": round((price / baseline - 1) * 100, 6),
        "source": TQ_SOURCE,
        "dataTimestamp": observed.isoformat(),
        "open": _finite(_value(quote, "open"), price),
        "high": _finite(_value(quote, "highest"), price),
        "low": _finite(_value(quote, "lowest"), price),
        "prevClose": previous_close if previous_close > 0 else baseline,
        "prevSettlement": settlement if settlement > 0 else baseline,
        "volume": max(0, int(_finite(_value(quote, "volume")))),
        "openInterest": max(0, int(_finite(_value(quote, "open_interest")))),
    }


def _nullable_positive(value: Any) -> float | None:
    number = _finite(value)
    return number if number > 0 else None


def quote_to_microstructure(
    symbol: str,
    quote: Any,
    trades: list[dict[str, Any]],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Convert only provider-observed depth fields; unavailable levels remain null."""
    observed = _observed_at(_value(quote, "datetime"), now)
    bids = [
        {
            "level": level,
            "price": _nullable_positive(_value(quote, f"bid_price{level}")),
            "volume": max(0, int(_finite(_value(quote, f"bid_volume{level}")))),
        }
        for level in range(1, 6)
    ]
    asks = [
        {
            "level": level,
            "price": _nullable_positive(_value(quote, f"ask_price{level}")),
            "volume": max(0, int(_finite(_value(quote, f"ask_volume{level}")))),
        }
        for level in range(1, 6)
    ]
    return {
        "symbol": symbol,
        "source": TQ_SOURCE,
        "dataStatus": "FRESH",
        "dataTimestamp": observed.isoformat(),
        "lastPrice": _nullable_positive(_value(quote, "last_price")),
        "bids": bids,
        "asks": asks,
        "trades": trades,
    }


def ticks_to_trades(rows: Any, limit: int = 80) -> list[dict[str, Any]]:
    """Derive exchange tick transactions from cumulative volume without synthetic rows."""
    records = rows.to_dict("records") if hasattr(rows, "to_dict") else list(rows)
    records = [row for row in records if int(_finite(_value(row, "id"), -1)) >= 0]
    trades: list[dict[str, Any]] = []
    for previous, current in zip(records, records[1:]):
        current_volume = max(0, int(_finite(_value(current, "volume"))))
        previous_volume = max(0, int(_finite(_value(previous, "volume"))))
        volume = current_volume - previous_volume
        price = _nullable_positive(_value(current, "last_price"))
        if volume <= 0 or price is None:
            continue
        ask = _nullable_positive(_value(current, "ask_price1"))
        bid = _nullable_positive(_value(current, "bid_price1"))
        side = "BUY" if ask is not None and price >= ask else (
            "SELL" if bid is not None and price <= bid else "NEUTRAL"
        )
        amount = max(0.0, _finite(_value(current, "amount")) - _finite(_value(previous, "amount")))
        open_interest_change = int(_finite(_value(current, "open_interest"))) - int(
            _finite(_value(previous, "open_interest"))
        )
        trades.append({
            "id": str(int(_finite(_value(current, "id")))),
            "timestamp": _observed_at(_value(current, "datetime")).isoformat(),
            "price": price,
            "volume": volume,
            "amount": round(amount, 2),
            "openInterest": max(0, int(_finite(_value(current, "open_interest")))),
            "openInterestChange": open_interest_change,
            "side": side,
        })
    return trades[-max(1, limit):][::-1]


def bars_to_history(rows: Any) -> list[dict[str, Any]]:
    """Convert a copied TqSdk kline serial (DataFrame or records) to daily bars."""
    records = rows.to_dict("records") if hasattr(rows, "to_dict") else list(rows)
    bars: list[dict[str, Any]] = []
    previous: float | None = None
    for row in records:
        close = _finite(_value(row, "close"))
        if close <= 0:
            continue
        observed = _observed_at(_value(row, "datetime"))
        bars.append({
            "timestamp": observed.isoformat(),
            "open": _finite(_value(row, "open"), close),
            "high": _finite(_value(row, "high"), close),
            "low": _finite(_value(row, "low"), close),
            "price": close,
            "volume": max(0, int(_finite(_value(row, "volume")))),
            "openInterest": max(0, int(_finite(_value(row, "close_oi", _value(row, "open_interest"))))),
            "change": round(close - previous, 6) if previous else 0,
            "changePct": round((close / previous - 1) * 100, 6) if previous else 0,
        })
        previous = close
    return bars


class TqSdkRealtimeFeed:
    """One authenticated TqSdk connection shared by all HTTP consumers."""

    def __init__(
        self,
        fallback: LiveMarketFeed | None = None,
        api_factory: Callable[[str, str], Any] | None = None,
    ) -> None:
        self.fallback = fallback or LiveMarketFeed()
        self.username = os.getenv("TQSDK_USERNAME", "").strip()
        self.password = os.getenv("TQSDK_PASSWORD", "")
        self.configured = bool(self.username and self.password)
        self.freshness_seconds = float(os.getenv("TQSDK_FRESHNESS_SECONDS", "15"))
        self.api_factory = api_factory
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.wake_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.connected = False
        self.last_event_at: str | None = None
        self.last_error: str | None = None
        self.quotes: dict[str, dict[str, Any]] = {}
        self.histories: dict[str, list[dict[str, Any]]] = {}
        self.microstructures: dict[str, dict[str, Any]] = {}
        self.microstructure_requested: set[str] = set()
        self.catalog: list[dict[str, Any]] = []
        self.catalog_timestamp: str | None = None
        self.provider_symbols: dict[str, str] = {}
        self.requested = {
            item.strip().upper()
            for item in os.getenv("MARKET_SYMBOLS", "IFM,RBM,MM,CJM,SIM,TM").split(",")
            if item.strip()
        }

    def start(self) -> None:
        self.fallback.start()
        if not self.configured or (self.thread and self.thread.is_alive()):
            if not self.configured:
                self.last_error = "TqSdk credentials are not configured"
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run, name="tqsdk-realtime-feed", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.wake_event.set()
        if self.thread:
            self.thread.join(timeout=10)
        self.fallback.stop()

    def watch(self, symbol: str) -> None:
        normalized = symbol.upper().strip()
        if not SYMBOL.fullmatch(normalized):
            raise ValueError("Invalid futures symbol")
        with self.lock:
            self.requested.add(normalized)
        self.fallback.watch(normalized)
        self.wake_event.set()

    def watch_microstructure(self, symbol: str) -> None:
        normalized = symbol.upper().strip()
        if not SYMBOL.fullmatch(normalized):
            raise ValueError("Invalid futures symbol")
        with self.lock:
            is_new = normalized not in self.microstructure_requested
            self.microstructure_requested.add(normalized)
        if is_new:
            self.wake_event.set()

    def _new_api(self) -> Any:
        if self.api_factory:
            return self.api_factory(self.username, self.password)
        from tqsdk import TqApi, TqAuth

        return TqApi(auth=TqAuth(self.username, self.password))

    def _build_catalog(self, futures: list[str], continuous: list[str]) -> tuple[list[dict], dict[str, str]]:
        providers: dict[str, str] = {}
        products: dict[tuple[str, str], dict[str, Any]] = {}
        for provider_symbol in futures:
            try:
                exchange, root = provider_product(provider_symbol)
                symbol = canonical_symbol(provider_symbol)
            except ValueError:
                continue
            if not contract_maturity(symbol):
                continue
            providers[symbol] = provider_symbol
            group_exchange = "SHFE" if exchange == "INE" else exchange
            entry = products.setdefault((exchange, root), {
                "exchange": group_exchange,
                "exchangeName": TQ_EXCHANGE_NAMES.get(exchange, exchange),
                "name": root,
                "node": f"tq:{exchange}.{root}",
                "rootSymbol": root,
                "mainSymbol": f"{root}M",
                "contracts": [],
            })
            entry["contracts"].append(symbol)
        for provider_symbol in continuous:
            try:
                exchange, root = provider_product(provider_symbol)
                canonical = canonical_symbol(provider_symbol)
            except ValueError:
                continue
            providers[canonical] = provider_symbol
            entry = products.get((exchange, root))
            if entry:
                entry["mainSymbol"] = canonical
        resolved = []
        exchange_order = {"SHFE": 0, "DCE": 1, "CZCE": 2, "CFFEX": 3, "GFEX": 4}
        for entry in products.values():
            entry["contracts"].sort(key=lambda item: contract_maturity(item) or "9999-99-99")
            resolved.append(entry)
        resolved.sort(key=lambda item: (exchange_order.get(item["exchange"], 99), item["rootSymbol"]))
        return resolved, providers

    @staticmethod
    def _decorate_catalog_names(catalog: list[dict[str, Any]], quotes: dict[str, Any]) -> None:
        """Use provider metadata already returned by the batch quote subscription."""
        for entry in catalog:
            quote = quotes.get(entry["mainSymbol"])
            name = str(_value(quote, "instrument_name", "") or "") if quote is not None else ""
            if name:
                entry["name"] = re.sub(r"\d+|主连|连续", "", name).strip() or entry["name"]

    @staticmethod
    def _subscribe_quotes(api: Any, providers: dict[str, str]) -> dict[str, Any]:
        provider_items = list(providers.items())
        quote_list = api.get_quote_list([provider for _, provider in provider_items])
        return {
            canonical: entity
            for (canonical, _), entity in zip(provider_items, quote_list, strict=True)
        }

    def _run_session(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        api = None
        try:
            api = self._new_api()
            futures = list(api.query_quotes(ins_class="FUTURE", expired=False))
            continuous = list(api.query_quotes(ins_class="CONT"))
            catalog, providers = self._build_catalog(futures, continuous)
            if not catalog or not providers:
                raise RuntimeError("TqSdk returned an empty futures catalog")
            # TqSdk waits for every get_quote call. Calling it once per contract makes
            # full-market startup take minutes, so subscribe to the complete observed
            # catalog in one provider-supported batch instead.
            quote_entities = self._subscribe_quotes(api, providers)
            self._decorate_catalog_names(catalog, quote_entities)
            initial_quotes: dict[str, dict[str, Any]] = {}
            initial_microstructures: dict[str, dict[str, Any]] = {}
            for symbol, entity in quote_entities.items():
                try:
                    initial_quotes[symbol] = quote_to_snapshot(symbol, entity)
                    initial_microstructures[symbol] = quote_to_microstructure(symbol, entity, [])
                except ValueError:
                    continue
            connected_at = datetime.now(SHANGHAI).isoformat()
            initial_event_at = _latest_timestamp(
                *(item["dataTimestamp"] for item in initial_quotes.values())
            )
            kline_entities: dict[str, Any] = {}
            tick_entities: dict[str, Any] = {}
            with self.lock:
                self.catalog = catalog
                self.catalog_timestamp = connected_at
                self.provider_symbols = providers
                self.quotes.update(initial_quotes)
                self.microstructures.update(initial_microstructures)
                self.connected = True
                self.last_event_at = initial_event_at
                self.last_error = None

            while not self.stop_event.is_set():
                with self.lock:
                    requested = set(self.requested)
                    microstructure_requested = set(self.microstructure_requested)
                for symbol in sorted(requested):
                    provider = providers.get(symbol)
                    if provider and symbol not in kline_entities:
                        serial = api.get_kline_serial(provider, 86400, data_length=2000)
                        kline_entities[symbol] = serial
                        # The synchronous call has already received the initial series.
                        # During a closed market there may be no later change event, so
                        # persist it immediately instead of waiting indefinitely.
                        bars = bars_to_history(serial.copy())
                        if bars:
                            with self.lock:
                                self.histories[symbol] = bars

                for symbol in sorted(microstructure_requested):
                    provider = providers.get(symbol)
                    if provider and symbol not in tick_entities:
                        serial = api.get_tick_serial(provider, data_length=200)
                        tick_entities[symbol] = serial
                        trades = ticks_to_trades(serial.copy())
                        entity = quote_entities.get(symbol)
                        if entity is not None:
                            snapshot = quote_to_microstructure(symbol, entity, trades)
                            with self.lock:
                                self.microstructures[symbol] = snapshot

                changed = api.wait_update(deadline=time.time() + 1)
                if not changed:
                    continue
                updated_quotes: dict[str, dict[str, Any]] = {}
                updated_microstructures: dict[str, dict[str, Any]] = {}
                for symbol, entity in quote_entities.items():
                    if api.is_changing(entity, ["last_price", "datetime", "volume", "open_interest"]):
                        try:
                            updated_quotes[symbol] = quote_to_snapshot(symbol, entity)
                        except ValueError:
                            continue
                    if symbol in microstructure_requested and api.is_changing(entity, [
                        "datetime", "last_price",
                        *[f"bid_price{level}" for level in range(1, 6)],
                        *[f"bid_volume{level}" for level in range(1, 6)],
                        *[f"ask_price{level}" for level in range(1, 6)],
                        *[f"ask_volume{level}" for level in range(1, 6)],
                    ]):
                        with self.lock:
                            trades = list(self.microstructures.get(symbol, {}).get("trades", []))
                        updated_microstructures[symbol] = quote_to_microstructure(symbol, entity, trades)
                updated_histories: dict[str, list[dict[str, Any]]] = {}
                for symbol, serial in kline_entities.items():
                    if api.is_changing(serial):
                        bars = bars_to_history(serial.copy())
                        if bars:
                            updated_histories[symbol] = bars
                for symbol, serial in tick_entities.items():
                    if api.is_changing(serial):
                        entity = quote_entities.get(symbol)
                        if entity is not None:
                            updated_microstructures[symbol] = quote_to_microstructure(
                                symbol, entity, ticks_to_trades(serial.copy())
                            )
                if updated_quotes or updated_histories or updated_microstructures:
                    event_at = _latest_timestamp(
                        self.last_event_at,
                        *(item["dataTimestamp"] for item in updated_quotes.values()),
                        *(bars[-1]["timestamp"] for bars in updated_histories.values() if bars),
                    )
                    with self.lock:
                        self.quotes.update(updated_quotes)
                        self.histories.update(updated_histories)
                        self.microstructures.update(updated_microstructures)
                        self.last_event_at = event_at
        finally:
            with self.lock:
                self.connected = False
            if api is not None:
                try:
                    api.close()
                except Exception:
                    logger.warning("tqsdk_close_failed", exc_info=True)
            loop.close()

    def _run(self) -> None:
        delays = (2, 5, 15, 30)
        failure_count = 0
        while not self.stop_event.is_set():
            try:
                self._run_session()
                failure_count = 0
            except Exception as error:
                failure_count += 1
                with self.lock:
                    self.connected = False
                    self.last_error = f"TqSdk connection failed ({type(error).__name__})"
                logger.warning("tqsdk_session_failed error_type=%s", type(error).__name__)
            if not self.stop_event.is_set():
                self.stop_event.wait(delays[min(failure_count - 1, len(delays) - 1)])

    @staticmethod
    def _degrade_quote(item: dict[str, Any] | None) -> dict[str, Any] | None:
        if not item:
            return None
        degraded = dict(item)
        degraded["dataStatus"] = "DEGRADED"
        source = str(degraded.get("source", "公开行情源"))
        degraded["source"] = source if source.endswith(FALLBACK_SUFFIX) else source + FALLBACK_SUFFIX
        return degraded

    def _primary_quote(self, symbol: str) -> dict[str, Any] | None:
        with self.lock:
            item = self.quotes.get(symbol)
            connected = self.connected
        if not item:
            return None
        result = dict(item)
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(result["dataTimestamp"])).total_seconds()
        result["dataStatus"] = "FRESH" if connected and age <= self.freshness_seconds else "CACHED"
        return result

    def snapshot(self, symbol: str) -> dict[str, Any]:
        self.watch(symbol)
        normalized = symbol.upper()
        quote = self._primary_quote(normalized)
        with self.lock:
            history = list(self.histories.get(normalized, []))
            primary_quotes = {key: dict(value) for key, value in self.quotes.items()}
        if quote:
            root = root_symbol(normalized)
            contracts = [
                {"contract": key, "maturityDate": contract_maturity(key), "price": item["price"],
                 "dataTimestamp": item["dataTimestamp"]}
                for key, item in primary_quotes.items()
                if root_symbol(key) == root and contract_maturity(key)
            ]
            if not history:
                # Quote delivery must not wait for the larger daily-bar download.
                # The fallback history is still observed public-market data and is
                # replaced atomically as soon as the TqSdk serial is initialized.
                history = list(self.fallback.snapshot(normalized).get("history", []))
            return {"quote": quote, "history": history,
                    "contracts": sorted(contracts, key=lambda item: item["maturityDate"])}
        fallback = self.fallback.snapshot(normalized)
        fallback["quote"] = self._degrade_quote(fallback.get("quote"))
        return fallback

    def microstructure_snapshot(self, symbol: str) -> dict[str, Any]:
        """Return provider-observed live depth and trades; never use public fallback data."""
        normalized = symbol.upper().strip()
        self.watch_microstructure(normalized)
        with self.lock:
            snapshot = copy.deepcopy(self.microstructures.get(normalized))
            connected = self.connected
        if not snapshot:
            raise ValueError(f"TqSdk microstructure for {normalized} is still warming up")
        observed = datetime.fromisoformat(snapshot["dataTimestamp"])
        age = (datetime.now(timezone.utc) - observed.astimezone(timezone.utc)).total_seconds()
        snapshot["dataStatus"] = "FRESH" if connected and age <= self.freshness_seconds else "CACHED"
        return snapshot

    def term_snapshot(self, root: str) -> dict[str, Any]:
        normalized_root = root_symbol(root)
        with self.lock:
            connected = self.connected
            contracts = [
                {"contract": key, "maturityDate": contract_maturity(key), "price": item["price"],
                 "dataTimestamp": item["dataTimestamp"]}
                for key, item in self.quotes.items()
                if root_symbol(key) == normalized_root and contract_maturity(key)
            ]
        contracts.sort(key=lambda item: item["maturityDate"])
        if contracts:
            observed = max(item["dataTimestamp"] for item in contracts)
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(observed)).total_seconds()
            return {"rootSymbol": normalized_root,
                    "dataStatus": "FRESH" if connected and age <= self.freshness_seconds else "CACHED",
                    "dataTimestamp": observed, "contracts": contracts}
        fallback = self.fallback.term_snapshot(normalized_root)
        fallback["dataStatus"] = "DEGRADED"
        return fallback

    def catalog_snapshot(self) -> dict[str, Any]:
        with self.lock:
            catalog = [dict(item) for item in self.catalog]
            observed = self.catalog_timestamp
            connected = self.connected
        if not catalog:
            fallback = self.fallback.catalog_snapshot()
            fallback["source"] = str(fallback["source"]) + FALLBACK_SUFFIX
            fallback["dataStatus"] = "DEGRADED"
            return fallback
        exchanges = []
        for exchange, exchange_name in EXCHANGES.values():
            exchanges.append({"code": exchange, "name": exchange_name,
                              "instruments": [item for item in catalog if item["exchange"] == exchange]})
        return {"source": "天勤 TqSdk 合约目录", "dataStatus": "FRESH" if connected else "DEGRADED",
                "dataTimestamp": observed, "exchanges": exchanges}

    def product(self, symbol: str) -> dict[str, Any] | None:
        root = root_symbol(symbol)
        with self.lock:
            item = next((dict(value) for value in self.catalog if value["rootSymbol"] == root), None)
        return item or self.fallback.product(symbol)

    def provider_symbol(self, symbol: str) -> str | None:
        """Resolve a public canonical symbol to its exact TqSdk instrument."""
        normalized = symbol.upper().strip()
        candidates = [normalized]
        if normalized.endswith("0"):
            candidates.append(f"{normalized[:-1]}M")
        elif normalized.endswith("M"):
            candidates.append(f"{normalized[:-1]}0")
        with self.lock:
            for candidate in candidates:
                provider = self.provider_symbols.get(candidate)
                if provider:
                    return provider
        return None

    def prediction_inputs(self, symbol: str):
        snapshot = self.snapshot(symbol)
        item, history = snapshot["quote"], snapshot["history"]
        if not item or not history:
            raise ValueError("Market collection is warming up; no observed quote/history available")
        quote = MarketQuote(
            symbol=symbol, name=item["displayName"], price=item["price"], change=item["change"],
            change_pct=item["changePct"], open=item["open"], high=item["high"], low=item["low"],
            prev_close=item["prevClose"], prev_settlement=item["prevSettlement"], volume=item["volume"],
            turnover=0, open_interest=item["openInterest"], timestamp=datetime.fromisoformat(item["dataTimestamp"]),
            is_live=item["dataStatus"] == "FRESH",
        )
        bars = [KLineBar(datetime.fromisoformat(bar["timestamp"]), bar["open"], bar["high"], bar["low"],
                         bar["price"], bar["volume"], bar["openInterest"]) for bar in history[-60:]]
        status = item["dataStatus"]
        if (datetime.now(timezone.utc) - bars[-1].timestamp).total_seconds() > 4 * 86400:
            status = "DEGRADED"
        return quote, bars, status

    def provider_status(self) -> dict[str, Any]:
        with self.lock:
            connected = self.connected
            return {
                "provider": "TQSDK",
                "configured": self.configured,
                "connected": connected,
                "lastEventAt": self.last_event_at,
                "fallbackActive": not connected,
                "message": "TqSdk real-time session connected" if connected else (
                    self.last_error or "TqSdk real-time session is not connected"
                ),
            }


def create_market_feed() -> LiveMarketFeed | TqSdkRealtimeFeed:
    provider = os.getenv("MARKET_DATA_PROVIDER", "tqsdk").strip().lower()
    return TqSdkRealtimeFeed() if provider == "tqsdk" else LiveMarketFeed()
