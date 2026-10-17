"""Auditable TqSdk data for daily futures backtests.

Continuous prices are kept separately for signals. Execution bars are fetched
from the actual delivery contract; a dominant-contract label is never treated
as evidence that continuous OHLC represents that delivery contract.
"""
from __future__ import annotations

import json
import math
import os
import tempfile
import threading
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

from data.data_feed import KLineBar
from data.live_feed import SHANGHAI
from data.tqsdk_feed import canonical_symbol
from data.trading_day import completed_daily_bar


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
    signal_bars: list[KLineBar] = field(default_factory=list)


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

    def _cache_path(self, symbol: str, start_date: date | None = None,
                    end_date: date | None = None) -> Path:
        safe = symbol.upper().replace("@", "_").replace(".", "_")
        if start_date or end_date:
            safe += f"_{start_date or 'start'}_{end_date or 'end'}"
        return self.cache_dir / f"{safe}_real_roll_daily.json"

    def _read_cache(self, path: Path, n: int, *, allow_stale: bool = False) -> TqSdkBacktestDataset | None:
        if not path.exists():
            return None
        age = datetime.now(SHANGHAI).timestamp() - path.stat().st_mtime
        if not allow_stale and age > self.cache_ttl_seconds:
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("schema_version") != 2 or payload.get("price_basis") != "OBSERVED_DELIVERY_CONTRACT":
                return None
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
            signal_bars = [KLineBar(
                timestamp=datetime.fromisoformat(item["timestamp"]).astimezone(SHANGHAI),
                open=item["open"], high=item["high"], low=item["low"], close=item["close"],
                volume=item["volume"], open_interest=item["open_interest"],
            ) for item in payload["signal_bars"]]
            if [b.timestamp for b in bars] != [b.timestamp for b in signal_bars]:
                return None
            return TqSdkBacktestDataset(
                symbol=payload["symbol"],
                provider_symbol=payload["provider_symbol"],
                source=payload["source"],
                generated_at=datetime.fromisoformat(payload["generated_at"]),
                bars=bars,
                roll_events=events,
                contract_specs=specs,
                complete=bool(payload.get("complete", False)),
                signal_bars=signal_bars,
            )
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return None

    def cached_replay(self, symbol: str, start_date: date | None = None,
                      end_date: date | None = None) -> TqSdkBacktestDataset | None:
        """Read immutable observed history, independent of the current feed or cache TTL.

        Historical paper replay and backtests share this evidence. Current
        quotes retain their separate freshness requirements.
        """
        normalized = symbol.strip().upper()
        if normalized.endswith('M'):
            normalized = normalized[:-1] + '0'
        if not normalized.isalnum():
            return None
        paths = [self._cache_path(normalized), *sorted(self.cache_dir.glob(f'{normalized}_*_real_roll_daily.json'))]
        candidates = []
        for path in dict.fromkeys(paths):
            dataset = self._read_cache(path, 0, allow_stale=True)
            if dataset is None or not dataset.complete or dataset.symbol != normalized:
                continue
            bars = dataset.bars
            if not bars or any(
                not bar.contract_symbol or bar.contract_symbol not in dataset.contract_specs
                or not all(math.isfinite(v) and v > 0 for v in (bar.open, bar.high, bar.low, bar.close))
                or not bar.low <= min(bar.open, bar.close) <= max(bar.open, bar.close) <= bar.high
                or not completed_daily_bar(bar.timestamp)
                for bar in bars
            ):
                continue
            if any(a.timestamp >= b.timestamp for a, b in zip(bars, bars[1:])):
                continue
            if any(spec.volume_multiple <= 0 or not all(math.isfinite(v) and v > 0
                   for v in (spec.price_tick, spec.margin_per_lot))
                   or not math.isfinite(spec.commission_per_lot) or spec.commission_per_lot < 0
                   for spec in dataset.contract_specs.values()):
                continue
            if any(event.from_contract not in dataset.contract_specs
                   or event.to_contract not in dataset.contract_specs
                   or not all(math.isfinite(v) and v > 0 for v in (event.old_open, event.new_open))
                   for event in dataset.roll_events):
                continue
            selected = [b for b in bars if (start_date is None or b.timestamp.date() >= start_date)
                        and (end_date is None or b.timestamp.date() <= end_date)]
            if len(selected) >= 2:
                candidates.append((len(selected), dataset))
        return max(candidates, key=lambda item: item[0])[1] if candidates else None

    def replay_catalog(self) -> list[dict[str, Any]]:
        symbols = sorted({path.name.split('_')[0] for path in self.cache_dir.glob('*_real_roll_daily.json')})
        result = []
        for symbol in symbols:
            dataset = self.cached_replay(symbol)
            if dataset is not None:
                result.append({'symbol': symbol, 'totalBars': len(dataset.bars),
                               'startDate': dataset.bars[0].timestamp.date().isoformat(),
                               'endDate': dataset.bars[-1].timestamp.date().isoformat(),
                               'source': dataset.source, 'generatedAt': dataset.generated_at.isoformat()})
        return result

    def _write_cache(self, path: Path, dataset: TqSdkBacktestDataset, n: int) -> None:
        payload = {
            "schema_version": 2,
            "price_basis": "OBSERVED_DELIVERY_CONTRACT",
            "symbol": dataset.symbol,
            "provider_symbol": dataset.provider_symbol,
            "source": dataset.source,
            "generated_at": dataset.generated_at.isoformat(),
            "requested_bars": n,
            "complete": dataset.complete,
            "signal_bars": [{**asdict(bar), "timestamp": bar.timestamp.isoformat()}
                            for bar in dataset.signal_bars],
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
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> TqSdkBacktestDataset:
        # Atomic cache replacement makes completed datasets safe to read while
        # another symbol downloads. A slow cold load must not block warm replays.
        if not force_download:
            cached = self._read_cache(self._cache_path(symbol), n)
            if cached is not None:
                return cached
            cached = self._read_cache(self._cache_path(symbol, start_date, end_date), n)
            if cached is not None:
                return cached
        # TqSdk sessions and atomic cache creation are serialized. API request
        # concurrency is still handled above this layer, while identical cold
        # downloads collapse into one provider request followed by cache hits.
        with self._load_lock:
            return self._load(symbol, provider_symbol, n, force_download, start_date, end_date)

    def _load(
        self,
        symbol: str,
        provider_symbol: str,
        n: int = 2000,
        force_download: bool = False,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> TqSdkBacktestDataset:
        cache_path = self._cache_path(symbol, start_date, end_date)
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
            signal_bars: list[KLineBar] = []
            for row in main_rows:
                if _finite(_value(row, "datetime")) <= 0:
                    continue
                observed = _trading_datetime(_value(row, "datetime"))
                if not completed_daily_bar(observed):
                    continue
                if (start_date and observed.date() < start_date) or (end_date and observed.date() > end_date):
                    continue
                provider_contract = provider_by_date.get(observed.date())
                close = _finite(_value(row, "close"))
                if not provider_contract or close <= 0:
                    continue
                open_price = _finite(_value(row, "open"), close)
                high = _finite(_value(row, "high"), close)
                low = _finite(_value(row, "low"), close)
                if open_price <= 0 or high < max(open_price, close) or low > min(open_price, close):
                    continue
                signal_bars.append(KLineBar(
                    timestamp=observed,
                    open=open_price,
                    high=high,
                    low=low,
                    close=close,
                    volume=max(0, int(_finite(_value(row, "volume")))),
                    open_interest=max(0, int(_finite(_value(row, "close_oi")))),
                ))
            signal_bars.sort(key=lambda b: b.timestamp)
            if not signal_bars:
                raise TqSdkBacktestUnavailable(f"Insufficient TqSdk daily history for {symbol}")

            # Query each delivery independently. Multi-contract serials can
            # truncate older overlapping history and are not execution bars.
            mapping_rows = [(b.timestamp.date(), provider_by_date[b.timestamp.date()]) for b in signal_bars]
            provider_contracts = list(dict.fromkeys(contract for _, contract in mapping_rows))
            delivery: dict[str, dict[date, KLineBar]] = {}
            for contract in provider_contracts:
                rows = _records(api.get_kline_serial(contract, 86400, data_length=10000).copy())
                by_date: dict[date, KLineBar] = {}
                for row in rows:
                    if _finite(_value(row, "datetime")) <= 0:
                        continue
                    observed = _trading_datetime(_value(row, "datetime"))
                    values = [_finite(_value(row, key)) for key in ("open", "high", "low", "close")]
                    op, hi, lo, cl = values
                    if min(values) <= 0 or hi < max(op, cl, lo) or lo > min(op, cl, hi):
                        continue
                    by_date[observed.date()] = KLineBar(
                        observed, op, hi, lo, cl,
                        max(0, int(_finite(_value(row, "volume")))),
                        max(0, int(_finite(_value(row, "close_oi")))), canonical_symbol(contract),
                    )
                delivery[contract] = by_date

            roll_events: list[RollEvent] = []
            for index in range(1, len(mapping_rows)):
                roll_date, to_provider = mapping_rows[index]
                _, from_provider = mapping_rows[index - 1]
                if from_provider == to_provider:
                    continue
                old = delivery[from_provider].get(roll_date)
                new = delivery[to_provider].get(roll_date)
                if old is None or new is None:
                    raise IncompleteRollData(f"Real roll on {roll_date} requires observed prices for both tradable legs")
                gap = new.open - old.open
                roll_events.append(RollEvent(
                    execution_date=roll_date, from_contract=old.contract_symbol,
                    to_contract=new.contract_symbol, old_open=old.open, new_open=new.open,
                    price_gap=gap, price_gap_pct=gap / old.open * 100.0,
                    old_high=old.high, old_low=old.low, new_high=new.high, new_low=new.low,
                ))
            bars: list[KLineBar] = []
            for day, contract in mapping_rows:
                bar = delivery[contract].get(day)
                if bar is None:
                    raise TqSdkBacktestUnavailable(f"Missing observed delivery OHLC for {contract} on {day}")
                bars.append(bar)
            specs = self._specs(api, provider_contracts)

            dataset = TqSdkBacktestDataset(
                symbol=symbol.upper(),
                provider_symbol=provider_symbol,
                source="TQSDK_REAL_DOMINANT_DAILY",
                generated_at=datetime.now(SHANGHAI),
                bars=bars,
                roll_events=roll_events,
                contract_specs=specs,
                complete=True,
                signal_bars=signal_bars,
            )
            self._write_cache(cache_path, dataset, n)
            return dataset
        finally:
            api.close()
