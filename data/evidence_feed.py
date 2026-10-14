"""Cached collectors for auditable external evidence used by empirical engines.

B9 fix: _TtlCache now uses per-key locks (double-checked locking pattern) to
prevent concurrent threads from calling the same loader more than once per TTL
period, avoiding redundant network requests that could trigger rate-limiting.
"""

from __future__ import annotations

import json
import re
import threading
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from html import unescape
from time import monotonic
from typing import Any, Callable


SHANGHAI_TZ = timezone(timedelta(hours=8))


@dataclass(frozen=True)
class EvidenceBatch:
    key: str
    source_name: str
    source_url: str
    observed_at: datetime
    records: list[dict[str, Any]] = field(default_factory=list)
    status: str = "FRESH"

    @property
    def sample_size(self) -> int:
        return len(self.records)


class _TtlCache:
    """Thread-safe TTL cache with per-key locking.

    Guarantees that exactly one loader call is in flight for each cache key
    at any given time (double-checked locking).  Concurrent callers for the
    same key will block until the first load completes, then share its result.
    """

    def __init__(self) -> None:
        self._values: dict[str, tuple[float, EvidenceBatch]] = {}
        self._global_lock = threading.Lock()
        self._key_locks: dict[str, threading.Lock] = {}

    def _key_lock(self, key: str) -> threading.Lock:
        with self._global_lock:
            if key not in self._key_locks:
                self._key_locks[key] = threading.Lock()
            return self._key_locks[key]

    def get_or_load(
        self,
        key: str,
        ttl_seconds: int,
        loader: Callable[[], EvidenceBatch],
    ) -> EvidenceBatch:
        # Fast path: check without acquiring the per-key lock
        now = monotonic()
        with self._global_lock:
            current = self._values.get(key)
            if current and current[0] > now:
                return current[1]

        # Slow path: acquire per-key lock, then re-check (double-checked locking)
        with self._key_lock(key):
            now = monotonic()
            with self._global_lock:
                current = self._values.get(key)
                if current and current[0] > now:
                    return current[1]
            value = loader()
            with self._global_lock:
                self._values[key] = (monotonic() + ttl_seconds, value)
            return value


class EvidenceFeed:
    """Fetches only observed upstream values and never fabricates fallback records."""

    WEATHER_URL = (
        "https://api.open-meteo.com/v1/forecast?"
        "latitude=39.02,41.17,39.47&longitude=88.17,80.26,75.99&"
        "daily=temperature_2m_max,temperature_2m_min,precipitation_sum,"
        "relative_humidity_2m_mean&timezone=Asia%2FShanghai&forecast_days=3"
    )
    NEWS_URL = (
        "https://np-listapi.eastmoney.com/comm/web/getNewsByScColumns?"
        "client=web&biz=web_news_sccol&scColumns=375&order=1&page_index=1&page_size=50&"
        "req_trace=aiquant&fields=code,showTime,title,mediaName,summary,url,uniqueUrl,Np_dst&types=1,20"
    )
    RULES_URL = "https://portal.eastmoneyfutures.com/pages/service/jyts.html"
    REGIONS = ("若羌", "阿克苏", "喀什")

    def __init__(self, timeout: int = 4) -> None:
        self.timeout = timeout
        self._cache = _TtlCache()

    def _request(self, url: str) -> bytes:
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
                "User-Agent": "Mozilla/5.0 (compatible; AI-QUANT/2.0; +local-research)",
            },
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return response.read()

    def _read_json(self, url: str) -> Any:
        return json.loads(self._request(url).decode("utf-8"))

    def _read_text(self, url: str) -> str:
        return self._request(url).decode("utf-8")

    def get_weather(self) -> EvidenceBatch:
        return self._cache.get_or_load("weather", 1800, self._load_weather)

    def _load_weather(self) -> EvidenceBatch:
        payload = self._read_json(self.WEATHER_URL)
        locations = payload if isinstance(payload, list) else [payload]
        records: list[dict[str, Any]] = []
        for region, location in zip(self.REGIONS, locations):
            daily = location.get("daily", {})
            columns = zip(
                daily.get("time", []),
                daily.get("temperature_2m_max", []),
                daily.get("temperature_2m_min", []),
                daily.get("precipitation_sum", []),
                daily.get("relative_humidity_2m_mean", []),
            )
            for day, maximum, minimum, precipitation, humidity in columns:
                records.append(
                    {
                        "region": region,
                        "date": day,
                        "temperature_max": float(maximum),
                        "temperature_min": float(minimum),
                        "precipitation": float(precipitation),
                        "humidity": float(humidity),
                    }
                )
        if not records:
            raise RuntimeError("Open-Meteo returned no production-region weather records")
        return EvidenceBatch(
            key="weather",
            source_name="Open-Meteo 多模型气象数据",
            source_url=self.WEATHER_URL,
            observed_at=datetime.now(timezone.utc),
            records=records,
        )

    def get_news(self) -> EvidenceBatch:
        return self._cache.get_or_load("news", 600, self._load_news)

    def _load_news(self) -> EvidenceBatch:
        payload = self._read_json(self.NEWS_URL)
        items = payload.get("data", {}).get("list", [])
        records: list[dict[str, Any]] = []
        for item in items:
            searchable = f"{item.get('title', '')} {item.get('summary', '')}"
            if not re.search(r"红枣|灰枣|枣农|枣价", searchable, flags=re.IGNORECASE):
                continue
            observed_at = datetime.strptime(item["showTime"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=SHANGHAI_TZ)
            records.append(
                {
                    "title": str(item.get("title", "")),
                    "summary": str(item.get("summary", "")),
                    "media_name": str(item.get("mediaName", "")),
                    "url": str(item.get("uniqueUrl") or item.get("url") or ""),
                    "observed_at": observed_at,
                }
            )
        if not records:
            raise RuntimeError("Eastmoney returned no red-date-related news records")
        return EvidenceBatch(
            key="news",
            source_name="东方财富红枣资讯",
            source_url="https://futures.eastmoney.com/a/acj.html",
            observed_at=max(record["observed_at"] for record in records).astimezone(timezone.utc),
            records=records,
        )

    def get_trading_rules(self) -> EvidenceBatch:
        return self._cache.get_or_load("trading_rules", 3600, self._load_trading_rules)

    def _load_trading_rules(self) -> EvidenceBatch:
        page = self._read_text(self.RULES_URL)
        row = re.search(r"(?is)<tr[^>]*>\s*<td>\s*红枣\s*</td>(.*?)</tr>", page)
        if row is None:
            raise RuntimeError("Current CJ trading-rule row was not found")
        cells = [
            unescape(re.sub(r"<[^>]+>", "", cell)).strip()
            for cell in re.findall(r"(?is)<td[^>]*>(.*?)</td>", row.group(0))
        ]
        if len(cells) < 5:
            raise RuntimeError("Current CJ trading-rule row was incomplete")
        limit_match = re.search(r"([0-9.]+)", cells[3])
        margin_match = re.search(r"([0-9.]+)", cells[4])
        if not limit_match or not margin_match:
            raise RuntimeError("Current CJ trading limits could not be parsed")
        contract_digits = cells[2]
        contract = f"CJ{contract_digits}" if contract_digits else "CJ"
        return EvidenceBatch(
            key="trading_rules",
            source_name="东方财富期货交易提示（交易所规则汇总）",
            source_url=self.RULES_URL,
            observed_at=datetime.now(timezone.utc),
            records=[
                {
                    "contract": contract,
                    "price_limit_pct": float(limit_match.group(1)),
                    "margin_pct": float(margin_match.group(1)),
                }
            ],
        )
