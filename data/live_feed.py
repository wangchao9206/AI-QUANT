"""Background collection of observed market data; no generated-data fallback."""
import json
import logging
import math
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from data.data_feed import KLineBar, MarketQuote

logger = logging.getLogger("AI-QUANT.LiveFeed")
SHANGHAI = ZoneInfo("Asia/Shanghai")
SYMBOL = re.compile(r"^[A-Z]{1,4}[A-Z0-9]{0,8}$")
DIRECTORY_URL = "https://vip.stock.finance.sina.com.cn/quotes_service/view/js/qihuohangqing.js"
CATALOG_URL = "https://vip.stock.finance.sina.com.cn/quotes_service/api/jsonp_v2.php/var%20_data=/Market_Center.getNameList"
EXCHANGES = {
    "shfe": ("SHFE", "上海期货交易所（含上海国际能源交易中心）"),
    "dce": ("DCE", "大连商品交易所"),
    "czce": ("CZCE", "郑州商品交易所"),
    "cffex": ("CFFEX", "中国金融期货交易所"),
    "gfex": ("GFEX", "广州期货交易所"),
}


def sina_symbol(symbol: str, now: datetime | None = None) -> str:
    """Translate canonical API symbols to Sina provider symbols."""
    normalized = symbol.upper().strip()
    if normalized.endswith("M"):
        return f"{normalized[:-1]}0"
    # TqSdk uses CZCE.CJ701 while Sina uses CJ2701 for the same delivery.
    # Keep the public API symbol intact and translate only the provider request.
    short_contract = re.fullmatch(r"([A-Z]{1,4})\d{3}", normalized)
    if short_contract:
        maturity = contract_maturity(normalized, now)
        if maturity:
            return f"{short_contract.group(1)}{maturity[2:4]}{maturity[5:7]}"
    return normalized


def root_symbol(symbol: str) -> str:
    normalized = symbol.upper().strip()
    if normalized.endswith("M") or re.fullmatch(r"[A-Z]{1,4}0", normalized):
        return normalized[:-1]
    return re.sub(r"\d+$", "", normalized)


def normalize_product_root(root: str) -> str:
    """Validate a product root without interpreting it as a continuous symbol.

    JM is the coking-coal root but also the canonical coke continuous symbol.
    Callers with a full instrument must resolve it with root_symbol first.
    """
    normalized = root.upper().strip()
    if not re.fullmatch(r"[A-Z]{1,4}", normalized):
        raise ValueError("Expected a product root, not a delivery or continuous symbol")
    return normalized


def contract_maturity(symbol: str, now: datetime | None = None) -> str | None:
    match = re.fullmatch(r"[A-Z]{1,4}(\d{3,4})", symbol.upper())
    if not match:
        return None
    digits = match.group(1)
    month = int(digits[-2:])
    if not 1 <= month <= 12:
        return None
    if len(digits) == 4:
        year = 2000 + int(digits[:2])
    else:
        current_year = (now or datetime.now(SHANGHAI)).year
        year = current_year // 10 * 10 + int(digits[0])
        if year < current_year - 1:
            year += 10
    return f"{year:04d}-{month:02d}-01"


def parse_product_nodes(payload: str) -> list[dict]:
    """Parse Sina's current exchange/product directory without guessing listings."""
    starts = list(re.finditer(r"(?m)^\s*(czce|dce|shfe|cffex|gfex)\s*:\s*\[", payload))
    products: list[dict] = []
    for index, match in enumerate(starts):
        exchange_key = match.group(1)
        end = starts[index + 1].start() if index + 1 < len(starts) else payload.find("// bohai", match.end())
        section = payload[match.end():end if end > 0 else len(payload)]
        exchange, exchange_name = EXCHANGES[exchange_key]
        for name, node in re.findall(r"\['([^']+)',\s*'([^']+_qh)'", section):
            products.append({"exchange": exchange, "exchangeName": exchange_name, "name": name, "node": node})
    if not products:
        raise ValueError("Provider product directory was empty")
    return products


def parse_contract_list(payload: str) -> list[str]:
    start, end = payload.find("["), payload.rfind("]")
    if start < 0 or end < start:
        raise ValueError("Provider contract list was invalid")
    rows = json.loads(payload[start:end + 1])
    symbols = []
    for row in rows:
        symbol = str(row.get("symbol", "")).upper().strip()
        if SYMBOL.fullmatch(symbol):
            symbols.append(symbol)
    return symbols


def parse_quotes(payload: str, requested: list[str]) -> dict[str, dict]:
    quotes = {}
    for symbol in requested:
        match = re.search(r'hq_str_nf_' + re.escape(symbol) + r'="([^"]*)"', payload)
        if not match:
            continue
        fields = match.group(1).split(",")
        try:
            financial_layout = bool(fields and re.fullmatch(r"-?\d+(?:\.\d+)?", fields[0]) and len(fields) >= 50)
            if financial_layout:
                price, settlement = float(fields[3]), float(fields[14])
                name, date_value, time_value = fields[49], fields[36], fields[37].replace(":", "")
                open_price, high, low = float(fields[0]), float(fields[1]), float(fields[2])
                previous_close, volume, open_interest = float(fields[13]), int(float(fields[4])), int(float(fields[6]))
            else:
                price, settlement = float(fields[8]), float(fields[10])
                name, date_value, time_value = fields[0], fields[17], fields[1].zfill(6)
                open_price, high, low = float(fields[2]), float(fields[3]), float(fields[4])
                previous_close, volume, open_interest = float(fields[5]), int(float(fields[14])), int(float(fields[13]))
            if not math.isfinite(price) or price <= 0 or settlement <= 0:
                continue
            observed = datetime.strptime(date_value + time_value, "%Y-%m-%d%H%M%S").replace(tzinfo=SHANGHAI)
            quotes[symbol] = {
                "symbol": symbol, "displayName": name, "price": price,
                "change": round(price - settlement, 6),
                "changePct": round((price / settlement - 1) * 100, 6),
                "source": "新浪期货", "dataTimestamp": observed.isoformat(),
                "open": open_price, "high": high, "low": low,
                "prevClose": previous_close, "prevSettlement": settlement,
                "volume": volume, "openInterest": open_interest,
            }
        except (IndexError, ValueError, OverflowError):
            logger.debug("invalid_quote symbol=%s", symbol)
    return quotes


def parse_history(payload: str) -> list[dict]:
    start, end = payload.find("["), payload.rfind("]")
    if start < 0 or end < start:
        raise ValueError("Upstream did not return daily bars")
    rows = json.loads(payload[start:end + 1])
    bars = []
    previous = None
    for row in rows:
        close = float(row["c"])
        if not math.isfinite(close) or close <= 0:
            continue
        bars.append({
            "timestamp": datetime.strptime(row["d"], "%Y-%m-%d").replace(tzinfo=SHANGHAI).isoformat(),
            "open": float(row["o"]), "high": float(row["h"]), "low": float(row["l"]),
            "price": close, "volume": int(float(row.get("v", 0))),
            "openInterest": int(float(row.get("p", 0))),
            "change": round(close - previous, 6) if previous else 0,
            "changePct": round((close / previous - 1) * 100, 6) if previous else 0,
        })
        previous = close
    if not bars:
        raise ValueError("No valid daily bars")
    return bars


class LiveMarketFeed:
    def __init__(self, cache_path: str | None = None):
        self.path = Path(cache_path or os.getenv("MARKET_FEED_CACHE", "/var/lib/aiquant/feed/snapshots.json"))
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.wake_event = threading.Event()
        self.thread = None
        self.quotes: dict[str, dict] = {}
        self.histories: dict[str, list[dict]] = {}
        self.catalog: list[dict] = []
        self.catalog_timestamp: str | None = None
        self.catalog_degraded = True
        self.catalog_updated = -86400.0
        self.failures: set[str] = set()
        self.history_updated: dict[str, float] = {}
        self.symbols = {
            item.strip().upper()
            for item in os.getenv("MARKET_SYMBOLS", "CJM,CJ2612,CJ2701,CJ2703,CJ2705").split(",")
            if item.strip()
        }
        self.history_symbols = set(self.symbols)
        self.client = httpx.Client(timeout=httpx.Timeout(8.0), headers={
            "User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn/",
        })
        try:
            stored = json.loads(self.path.read_text(encoding="utf-8"))
            self.quotes = stored.get("quotes", {})
            self.histories = stored.get("histories", {})
            self.catalog = stored.get("catalog", [])
            self.catalog_timestamp = stored.get("catalogTimestamp")
            if self.catalog:
                self._apply_catalog_symbols(self.catalog)
            self.failures.update(self.quotes)
        except (OSError, ValueError):
            pass

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run, name="market-feed", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.wake_event.set()
        if self.thread:
            self.thread.join(timeout=8)

    def watch(self, symbol: str):
        if not SYMBOL.fullmatch(symbol):
            raise ValueError("Invalid futures symbol")
        with self.lock:
            is_new = symbol not in self.symbols or symbol not in self.history_symbols
            if symbol not in self.symbols:
                self.symbols.add(symbol)
            self.history_symbols.add(symbol)
            if is_new:
                self.wake_event.set()

    def _apply_catalog_symbols(self, catalog: list[dict]) -> None:
        for product in catalog:
            self.symbols.add(product["mainSymbol"])
            self.symbols.update(product.get("contracts", []))

    def _load_product_contracts(self, product: dict) -> dict:
        response = self.client.get(CATALOG_URL, params={
            "page": 1, "num": 500, "sort": "symbol", "asc": 1, "node": product["node"],
        })
        response.raise_for_status()
        symbols = parse_contract_list(response.text)
        if not symbols:
            raise ValueError(f"No contracts returned for {product['node']}")
        provider_main = next((symbol for symbol in symbols if re.fullmatch(r"[A-Z]{1,4}0", symbol)), None)
        if provider_main is None:
            raise ValueError(f"No observed continuous contract returned for {product['node']}")
        root = root_symbol(provider_main)
        contracts = sorted(
            (symbol for symbol in symbols if root_symbol(symbol) == root and contract_maturity(symbol)),
            key=lambda symbol: contract_maturity(symbol) or "9999-99-99",
        )
        return {
            **product,
            "rootSymbol": root,
            "mainSymbol": f"{root}M",
            "contracts": contracts,
        }

    def refresh_catalog(self) -> None:
        try:
            response = self.client.get(DIRECTORY_URL)
            response.raise_for_status()
            products = parse_product_nodes(response.content.decode("gb18030"))
            resolved = []
            with ThreadPoolExecutor(max_workers=12) as pool:
                futures = [pool.submit(self._load_product_contracts, product) for product in products]
                for future in futures:
                    try:
                        resolved.append(future.result())
                    except (httpx.HTTPError, ValueError, KeyError) as error:
                        logger.warning("catalog_product_failed %s", error)
            if len(resolved) < 5:
                raise ValueError("Provider catalog did not cover all exchanges")
            exchange_order = {name: index for index, name in enumerate(EXCHANGES)}
            resolved.sort(key=lambda item: (exchange_order.get(item["exchange"].lower(), 99), item["rootSymbol"]))
            with self.lock:
                self.catalog = resolved
                self.catalog_timestamp = datetime.now(SHANGHAI).isoformat()
                self.catalog_degraded = False
                self._apply_catalog_symbols(resolved)
        except (httpx.HTTPError, ValueError, UnicodeError) as error:
            with self.lock:
                self.catalog_degraded = True
            logger.warning("catalog_refresh_failed %s", error)
        finally:
            self.catalog_updated = time.monotonic()

    def _refresh_quote_batch(self, provider_symbols: list[str]) -> dict[str, dict]:
        response = self.client.get("https://hq.sinajs.cn/list=" + ",".join("nf_" + symbol for symbol in provider_symbols))
        response.raise_for_status()
        return parse_quotes(response.content.decode("gb18030"), provider_symbols)

    def refresh(self):
        if time.monotonic() - self.catalog_updated >= float(os.getenv("MARKET_CATALOG_REFRESH_SECONDS", "21600")):
            self.refresh_catalog()
        with self.lock:
            symbols = sorted(self.symbols)
        aliases = {symbol: sina_symbol(symbol) for symbol in symbols}
        provider_symbols = sorted(set(aliases.values()))
        provider_quotes: dict[str, dict] = {}
        batches = [provider_symbols[index:index + 100] for index in range(0, len(provider_symbols), 100)]
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(self._refresh_quote_batch, batch) for batch in batches]
            for future in futures:
                try:
                    provider_quotes.update(future.result())
                except (httpx.HTTPError, ValueError, UnicodeError) as error:
                    logger.warning("quote_batch_refresh_failed %s", error)
        parsed = {
            symbol: {**provider_quotes[alias], "symbol": symbol}
            for symbol, alias in aliases.items() if alias in provider_quotes
        }
        with self.lock:
            self.quotes.update(parsed)
            self.failures.difference_update(parsed)
            self.failures.update(set(symbols) - set(parsed))

        with self.lock:
            history_symbols = list(self.history_symbols)
        due = [s for s in history_symbols if time.monotonic() - self.history_updated.get(s, -3600) >= 900]
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(self._refresh_history, due))
        with self.lock:
            stored = {
                "quotes": self.quotes,
                "histories": self.histories,
                "catalog": self.catalog,
                "catalogTimestamp": self.catalog_timestamp,
            }
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                temporary = self.path.with_suffix(".tmp")
                temporary.write_text(json.dumps(stored, ensure_ascii=False), encoding="utf-8")
                temporary.replace(self.path)
            except OSError as error:
                logger.warning("market_cache_persist_failed %s", error)

    def _refresh_history(self, symbol: str):
        try:
            response = self.client.get(
                "https://stock2.finance.sina.com.cn/futures/api/jsonp.php/var%20_data=/InnerFuturesNewService.getDailyKLine",
                params={"symbol": sina_symbol(symbol)},
            )
            response.raise_for_status()
            bars = parse_history(response.text)
            with self.lock:
                self.histories[symbol] = bars
                self.history_updated[symbol] = time.monotonic()
        except (httpx.HTTPError, ValueError, KeyError) as error:
            logger.warning("history_refresh_failed symbol=%s error=%s", symbol, error)
        finally:
            # A missing contract history must not become an immediate retry loop.
            # Keep the same 15-minute refresh budget used by successful requests.
            with self.lock:
                self.history_updated[symbol] = time.monotonic()

    def _run(self):
        while not self.stop_event.is_set():
            try:
                self.refresh()
            except Exception:
                logger.exception("market_refresh_failed")
            self.wake_event.wait(float(os.getenv("MARKET_REFRESH_SECONDS", "30")))
            self.wake_event.clear()

    def snapshot(self, symbol: str) -> dict:
        self.watch(symbol)
        root = root_symbol(symbol)
        with self.lock:
            quote = self.quotes.get(symbol)
            quote = dict(quote) if quote else None
            if quote:
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(quote["dataTimestamp"])).total_seconds()
                quote["dataStatus"] = "DEGRADED" if symbol in self.failures else ("FRESH" if age <= 120 else "CACHED")
            history = list(self.histories.get(symbol, []))
            contracts = []
            for name, item in self.quotes.items():
                maturity = contract_maturity(name)
                if root_symbol(name) == root and maturity:
                    contracts.append({"contract": name, "maturityDate": maturity,
                                      "price": item["price"], "dataTimestamp": item["dataTimestamp"]})
        return {"quote": quote, "history": history, "contracts": sorted(contracts, key=lambda item: item["maturityDate"])}

    def term_snapshot(self, root: str) -> dict:
        normalized_root = normalize_product_root(root)
        with self.lock:
            contracts = []
            degraded = False
            for name, item in self.quotes.items():
                maturity = contract_maturity(name)
                if root_symbol(name) != normalized_root or not maturity:
                    continue
                degraded = degraded or name in self.failures
                contracts.append({
                    "contract": name,
                    "maturityDate": maturity,
                    "price": item["price"],
                    "dataTimestamp": item["dataTimestamp"],
                })
        contracts.sort(key=lambda item: item["maturityDate"])
        observed = max((item["dataTimestamp"] for item in contracts), default=None)
        status = "CACHED"
        if degraded:
            status = "DEGRADED"
        elif observed:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(observed)).total_seconds()
            status = "FRESH" if age <= 120 else "CACHED"
        return {
            "rootSymbol": normalized_root,
            "dataStatus": status,
            "dataTimestamp": observed,
            "contracts": contracts,
        }

    def overview_snapshot(self) -> dict:
        with self.lock:
            catalog=[dict(item) for item in self.catalog]
            quotes={k:dict(v) for k,v in self.quotes.items()}
        items=[]
        for product in catalog:
            symbol=product['mainSymbol']
            quote=quotes.get(symbol)
            if quote:
                root=root_symbol(symbol)
                items.append({**quote,'symbol':root+'M','name':product['name'],
                    'exchange':product['exchange'],'contract':None,'dataStatus':'CACHED'})
        return {'items':items,'catalogCount':len(catalog),'connected':True,'source':'公开行情主连缓存'}

    def catalog_snapshot(self) -> dict:
        with self.lock:
            catalog = [dict(item) for item in self.catalog]
            observed = self.catalog_timestamp
            degraded = self.catalog_degraded
        exchanges = []
        for exchange, exchange_name in EXCHANGES.values():
            instruments = [item for item in catalog if item["exchange"] == exchange]
            exchanges.append({
                "code": exchange,
                "name": exchange_name,
                "instruments": instruments,
            })
        return {
            "source": "新浪期货公开目录",
            "dataStatus": "DEGRADED" if degraded else "FRESH",
            "dataTimestamp": observed,
            "exchanges": exchanges,
        }

    def product(self, symbol: str) -> dict | None:
        root = root_symbol(symbol)
        with self.lock:
            return next((dict(item) for item in self.catalog if item["rootSymbol"] == root), None)

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
