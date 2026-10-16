"""Auditable TqSdk data for daily futures backtests.

The continuous symbol is used only for signal generation. Every bar is tagged
with the delivery contract that TqSdk reported as dominant for that trading
day, and every roll contains observed prices for both tradable legs.
"""
from __future__ import annotations

import json
import math
import os
import tempfile
import threading
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

from data.data_feed import KLineBar
from data.live_feed import SHANGHAI
from data.tqsdk_feed import canonical_symbol


class TqSdkBacktestUnavailable(RuntimeError):
    """Raised when the authenticated historical execution dataset is unavailable."""


class IncompleteRollData(TqSdkBacktestUnavailable):
    """Raised rather than inventing a price for either leg of a roll."""


@dataclass(frozen=True)
class FuturesContractSpec:
    contract: str
    volume_multiple: int
    price_tick: float
    margin_per_lot: float
    commission_per_lot: float


@dataclass(frozen=True)
class RollEvent:
    execution_date: date
    from_contract: str
    to_contract: str
    old_open: float
    new_open: float
    price_gap: float
    price_gap_pct: float
    old_high: float | None = None
    old_low: float | None = None
    new_high: float | None = None
    new_low: float | None = None


@dataclass(frozen=True)
class TqSdkBacktestDataset:
    symbol: str
    provider_symbol: str
    source: str
    generated_at: datetime
    bars: list[KLineBar]
    roll_events: list[RollEvent]
    contract_specs: dict[str, FuturesContractSpec]
    complete: bool = True


def _value(item: Any, name: str, default: Any = None) -> Any:
    return item.get(name, default) if isinstance(item, dict) else getattr(item, name, default)


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def _trading_datetime(nanoseconds: Any) -> datetime:
    value = int(nanoseconds)
    return datetime.fromtimestamp(value / 1_000_000_000, SHANGHAI)


def _records(frame: Any) -> list[dict[str, Any]]:
    if hasattr(frame, "to_dict"):
        return list(frame.to_dict("records"))
    return [dict(item) for item in frame]


class TqSdkBacktestDataProvider:
    """Download and persist real dominant-contract execution evidence."""

    def __init__(
        self,
        cache_dir: Path | None = None,
        username: str | None = None,
        password: str | None = None,
        api_factory: Callable[[str, str], Any] | None = None,
        cache_ttl_seconds: int | None = None,
    ) -> None:
        history_root = Path(os.getenv("HISTORY_CACHE_DIR", "data/history"))
        self.cache_dir = cache_dir or history_root / "tqsdk-roll"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.username = (username if username is not None else os.getenv("TQSDK_USERNAME", "")).strip()
        self.password = password if password is not None else os.getenv("TQSDK_PASSWORD", "")
        self.api_factory = api_factory
        self._load_lock = threading.Lock()
        self.cache_ttl_seconds = cache_ttl_seconds or int(
            os.getenv("TQSDK_BACKTEST_CACHE_TTL_SECONDS", "43200")
        )

    def _new_api(self) -> Any:
        if not self.username or not self.password:
            raise TqSdkBacktestUnavailable("TqSdk credentials are required for real roll data")
        if self.api_factory:
            return self.api_factory(self.username, self.password)
        from tqsdk import TqApi, TqAuth

        return TqApi(auth=TqAuth(self.username, self.password))

    def _cache_path(self, symbol: str) -> Path:
        safe = symbol.upper().replace("@", "_").replace(".", "_")
        return self.cache_dir / f"{safe}_real_roll_daily.json"

    def _read_cache(self, path: Path, n: int) -> TqSdkBacktestDataset | None:
        if not path.exists():
            return None
        age = datetime.now(SHANGHAI).timestamp() - path.stat().st_mtime
        if age > self.cache_ttl_seconds:
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if int(payload.get("requested_bars", 0)) < n:
                return None
            bars = [
                KLineBar(
                    timestamp=datetime.fromisoformat(item["timestamp"]).astimezone(SHANGHAI),
                    open=float(item["open"]),
                    high=float(item["high"]),
                    low=float(item["low"]),
                    close=float(item["close"]),
                    volume=int(item["volume"]),
                    open_interest=int(item["open_interest"]),
                    contract_symbol=item["contract_symbol"],
                )
                for item in payload["bars"]
            ]
            events = [
                RollEvent(
                    execution_date=date.fromisoformat(item["execution_date"]),
                    from_contract=item["from_contract"],
                    to_contract=item["to_contract"],
                    old_open=float(item["old_open"]),
                    new_open=float(item["new_open"]),
                    price_gap=float(item["price_gap"]),
                    price_gap_pct=float(item["price_gap_pct"]),
                    old_high=float(item["old_high"]) if item.get("old_high") is not None else None,
                    old_low=float(item["old_low"]) if item.get("old_low") is not None else None,
                    new_high=float(item["new_high"]) if item.get("new_high") is not None else None,
                    new_low=float(item["new_low"]) if item.get("new_low") is not None else None,
                )
                for item in payload["roll_events"]
            ]
            specs = {
                key: FuturesContractSpec(**value)
                for key, value in payload["contract_specs"].items()
            }
            return TqSdkBacktestDataset(
                symbol=payload["symbol"],
                provider_symbol=payload["provider_symbol"],
                source=payload["source"],
                generated_at=datetime.fromisoformat(payload["generated_at"]),
                bars=bars,
                roll_events=events,
                contract_specs=specs,
                complete=bool(payload.get("complete", False)),
            )
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return None

    def _write_cache(self, path: Path, dataset: TqSdkBacktestDataset, n: int) -> None:
        payload = {
            "symbol": dataset.symbol,
            "provider_symbol": dataset.provider_symbol,
            "source": dataset.source,
            "generated_at": dataset.generated_at.isoformat(),
            "requested_bars": n,
            "complete": dataset.complete,
            "bars": [
                {
                    "timestamp": bar.timestamp.isoformat(),
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                    "open_interest": bar.open_interest,
                    "contract_symbol": bar.contract_symbol,
                }
                for bar in dataset.bars
            ],
            "roll_events": [
                {**asdict(event), "execution_date": event.execution_date.isoformat()}
                for event in dataset.roll_events
            ],
            "contract_specs": {
                key: asdict(spec) for key, spec in dataset.contract_specs.items()
            },
        }
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.cache_dir,
                prefix=f".{path.stem}_",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary = Path(handle.name)
                json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            temporary = None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    @staticmethod
    def _mapping(frame: Any, provider_symbol: str) -> list[tuple[date, str]]:
        result: list[tuple[date, str]] = []
        for row in _records(frame):
            raw_contract = str(_value(row, provider_symbol, "") or "").strip()
            raw_date = _value(row, "date")
            if not raw_contract or raw_date is None:
                continue
            trading_date = raw_date.date() if hasattr(raw_date, "date") else date.fromisoformat(str(raw_date)[:10])
            result.append((trading_date, raw_contract))
        return result

    @staticmethod
    def _specs(api: Any, provider_contracts: list[str]) -> dict[str, FuturesContractSpec]:
        entities = api.get_quote_list(provider_contracts)
        specs: dict[str, FuturesContractSpec] = {}
        for provider_contract, entity in zip(provider_contracts, entities, strict=True):
            contract = canonical_symbol(provider_contract)
            multiplier = int(_finite(_value(entity, "volume_multiple")))
            price_tick = _finite(_value(entity, "price_tick"))
            margin = _finite(_value(entity, "margin"))
            commission = _finite(_value(entity, "commission"))
            if multiplier <= 0 or price_tick <= 0 or margin <= 0 or commission < 0:
                raise TqSdkBacktestUnavailable(f"Incomplete contract specification for {contract}")
            specs[contract] = FuturesContractSpec(
                contract=contract,
                volume_multiple=multiplier,
                price_tick=price_tick,
                margin_per_lot=margin,
                commission_per_lot=commission,
            )
        return specs

    @staticmethod
    def _pair_prices(frame: Any, roll_date: date) -> tuple[float, float, float, float, float, float]:
        for row in _records(frame):
            if _trading_datetime(_value(row, "datetime")).date() != roll_date:
                continue
            old_open = _finite(_value(row, "open"))
            new_open = _finite(_value(row, "open1"))
            if old_open > 0 and new_open > 0:
                return (
                    old_open,
                    new_open,
                    _finite(_value(row, "high"), old_open),
                    _finite(_value(row, "low"), old_open),
                    _finite(_value(row, "high1"), new_open),
                    _finite(_value(row, "low1"), new_open),
                )
        raise IncompleteRollData(
            f"Real roll on {roll_date.isoformat()} requires observed prices for both tradable legs"
        )

    def load(
        self,
        symbol: str,
        provider_symbol: str,
        n: int = 2000,
        force_download: bool = False,
    ) -> TqSdkBacktestDataset:
        # TqSdk sessions and atomic cache creation are serialized. API request
        # concurrency is still handled above this layer, while identical cold
        # downloads collapse into one provider request followed by cache hits.
        with self._load_lock:
            return self._load(symbol, provider_symbol, n, force_download)

    def _load(
        self,
        symbol: str,
        provider_symbol: str,
        n: int = 2000,
        force_download: bool = False,
    ) -> TqSdkBacktestDataset:
        cache_path = self._cache_path(symbol)
        if not force_download:
            cached = self._read_cache(cache_path, n)
            if cached is not None:
                return cached

        api = self._new_api()
        try:
            mapping_rows = self._mapping(api.query_his_cont_quotes(provider_symbol, n=n), provider_symbol)
            if not mapping_rows:
                raise TqSdkBacktestUnavailable(f"No dominant-contract history for {symbol}")
            provider_by_date = dict(mapping_rows)
            main_rows = _records(api.get_kline_serial(provider_symbol, 86400, data_length=n).copy())
            bars: list[KLineBar] = []
            for row in main_rows:
                observed = _trading_datetime(_value(row, "datetime"))
                provider_contract = provider_by_date.get(observed.date())
                close = _finite(_value(row, "close"))
                if not provider_contract or close <= 0:
                    continue
                open_price = _finite(_value(row, "open"), close)
                high = _finite(_value(row, "high"), close)
                low = _finite(_value(row, "low"), close)
                if open_price <= 0 or high < max(open_price, close) or low > min(open_price, close):
                    continue
                bars.append(KLineBar(
                    timestamp=observed,
                    open=open_price,
                    high=high,
                    low=low,
                    close=close,
                    volume=max(0, int(_finite(_value(row, "volume")))),
                    open_interest=max(0, int(_finite(_value(row, "close_oi")))),
                    contract_symbol=canonical_symbol(provider_contract),
                ))
            if not bars:
                raise TqSdkBacktestUnavailable(f"Insufficient TqSdk daily history for {symbol}")

            provider_contracts = list(dict.fromkeys(contract for _, contract in mapping_rows))
            specs = self._specs(api, provider_contracts)
            roll_events: list[RollEvent] = []
            for index in range(1, len(mapping_rows)):
                roll_date, to_provider = mapping_rows[index]
                _, from_provider = mapping_rows[index - 1]
                if from_provider == to_provider:
                    continue
                pair = api.get_kline_serial(
                    [from_provider, to_provider],
                    86400,
                    data_length=n,
                ).copy()
                old_open, new_open, old_high, old_low, new_high, new_low = self._pair_prices(pair, roll_date)
                gap = new_open - old_open
                roll_events.append(RollEvent(
                    execution_date=roll_date,
                    from_contract=canonical_symbol(from_provider),
                    to_contract=canonical_symbol(to_provider),
                    old_open=old_open,
                    new_open=new_open,
                    price_gap=gap,
                    price_gap_pct=gap / old_open * 100.0,
                    old_high=old_high,
                    old_low=old_low,
                    new_high=new_high,
                    new_low=new_low,
                ))

            dataset = TqSdkBacktestDataset(
                symbol=symbol.upper(),
                provider_symbol=provider_symbol,
                source="TQSDK_REAL_DOMINANT_DAILY",
                generated_at=datetime.now(SHANGHAI),
                bars=bars,
                roll_events=roll_events,
                contract_specs=specs,
                complete=True,
            )
            self._write_cache(cache_path, dataset, n)
            return dataset
        finally:
            api.close()
