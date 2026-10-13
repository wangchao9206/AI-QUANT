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


def parse_quotes(payload: str, requested: list[str]) -> dict[str, dict]:
    quotes = {}
    for symbol in requested:
        match = re.search(r'hq_str_nf_' + re.escape(symbol) + r'="([^"]*)"', payload)
        if not match:
            continue
        fields = match.group(1).split(",")
        try:
            price, settlement = float(fields[8]), float(fields[10])
            if not math.isfinite(price) or price <= 0 or settlement <= 0:
                continue
            observed = datetime.strptime(fields[17] + fields[1].zfill(6), "%Y-%m-%d%H%M%S").replace(tzinfo=SHANGHAI)
            quotes[symbol] = {
                "symbol": symbol, "displayName": fields[0], "price": price,
                "change": round(price - settlement, 6),
                "changePct": round((price / settlement - 1) * 100, 6),
                "source": "新浪期货", "dataTimestamp": observed.isoformat(),
                "open": float(fields[2]), "high": float(fields[3]), "low": float(fields[4]),
                "prevClose": float(fields[5]), "prevSettlement": settlement,
                "volume": int(float(fields[14])), "openInterest": int(float(fields[13])),
            }
        except (IndexError, ValueError, OverflowError):
            logger.warning("invalid_quote symbol=%s", symbol)
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
    return bars[-240:]


class LiveMarketFeed:
    def __init__(self, cache_path: str | None = None):
        self.path = Path(cache_path or os.getenv("MARKET_FEED_CACHE", "/var/lib/aiquant/feed/snapshots.json"))
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.wake_event = threading.Event()
        self.thread = None
        self.quotes: dict[str, dict] = {}
        self.histories: dict[str, list[dict]] = {}
        self.failures: set[str] = set()
        self.history_updated: dict[str, float] = {}
        self.symbols = set(os.getenv("MARKET_SYMBOLS", "CJ2612,CJ2701,CJ2703,CJ2705").split(","))
        self.client = httpx.Client(timeout=httpx.Timeout(5.0), headers={
            "User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn/",
        })
        try:
            stored = json.loads(self.path.read_text(encoding="utf-8"))
            self.quotes = stored.get("quotes", {})
            self.histories = stored.get("histories", {})
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
            if symbol not in self.symbols:
                self.symbols.add(symbol)
                self.wake_event.set()

    def refresh(self):
        with self.lock:
            symbols = sorted(self.symbols)
        try:
            response = self.client.get("https://hq.sinajs.cn/list=" + ",".join("nf_" + s for s in symbols))
            response.raise_for_status()
            parsed = parse_quotes(response.content.decode("gb18030"), symbols)
            with self.lock:
                self.quotes.update(parsed)
                self.failures.difference_update(parsed)
                self.failures.update(set(symbols) - set(parsed))
        except (httpx.HTTPError, ValueError) as error:
            with self.lock:
                self.failures.update(symbols)
            logger.warning("quote_refresh_failed %s", error)

        due = [s for s in symbols if time.monotonic() - self.history_updated.get(s, -3600) >= 900]
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(self._refresh_history, due))
        with self.lock:
            stored = {"quotes": self.quotes, "histories": self.histories}
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
                params={"symbol": symbol},
            )
            response.raise_for_status()
            bars = parse_history(response.text)
            with self.lock:
                self.histories[symbol] = bars
                self.history_updated[symbol] = time.monotonic()
        except (httpx.HTTPError, ValueError, KeyError) as error:
            logger.warning("history_refresh_failed symbol=%s error=%s", symbol, error)

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
        root = re.sub(r"\d+$", "", symbol)
        with self.lock:
            quote = self.quotes.get(symbol)
            quote = dict(quote) if quote else None
            if quote:
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(quote["dataTimestamp"])).total_seconds()
                quote["dataStatus"] = "DEGRADED" if symbol in self.failures else ("FRESH" if age <= 120 else "CACHED")
            history = list(self.histories.get(symbol, []))
            contracts = []
            for name, item in self.quotes.items():
                match = re.fullmatch(re.escape(root) + r"(\d{2})(\d{2})", name)
                if match and 1 <= int(match[2]) <= 12:
                    contracts.append({"contract": name, "maturityDate": f"20{match[1]}-{match[2]}-01",
                                      "price": item["price"], "dataTimestamp": item["dataTimestamp"]})
        return {"quote": quote, "history": history, "contracts": sorted(contracts, key=lambda item: item["maturityDate"])}

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
