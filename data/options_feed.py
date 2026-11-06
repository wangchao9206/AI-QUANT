"""Observed-only options snapshots. All SDK calls belong to the existing feed worker."""
from __future__ import annotations

import copy
import logging
import math
import threading
import time
from datetime import datetime, timezone
from typing import Any
from data.options_live import OptionsLiveState

SOURCE = "天勤 TqSdk 期权行情"
EXCHANGES = {"SHFE", "INE", "DCE", "CZCE", "CFFEX", "GFEX"}
logger = logging.getLogger(__name__)


def number(value: Any, *, positive=False, nonnegative=False) -> float | None:
    try:
        n = float(value)
        if not math.isfinite(n) or (positive and n <= 0) or (nonnegative and n < 0):
            return None
        return n
    except (TypeError, ValueError):
        return None


def timestamp(value: Any) -> str | None:
    from data.live_feed import SHANGHAI
    try:
        if isinstance(value, str) and value.strip():
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt.replace(tzinfo=dt.tzinfo or SHANGHAI).isoformat()
        seconds = number(value, positive=True)
        return datetime.fromtimestamp(seconds, timezone.utc).isoformat() if seconds else None
    except (ValueError, OverflowError, OSError):
        return None


def quote_snapshot(entity: Any) -> dict:
    def get(key):
        return entity.get(key) if isinstance(entity, dict) else getattr(entity, key, None)
    return {
        "lastPrice": number(get("last_price"), nonnegative=True),
        "bidPrice": number(get("bid_price1"), positive=True),
        "askPrice": number(get("ask_price1"), positive=True),
        "bidVolume": number(get("bid_volume1"), nonnegative=True),
        "askVolume": number(get("ask_volume1"), nonnegative=True),
        "volume": number(get("volume"), nonnegative=True),
        "openInterest": number(get("open_interest"), nonnegative=True),
        "dataTimestamp": timestamp(get("datetime")),
        "exerciseType": get("exercise_type") if get("exercise_type") in ("A", "E") else None,
    }


def freshness(observed: str | None, connected: bool, seconds: float, now: datetime) -> str:
    if not observed:
        return "UNAVAILABLE"
    age = (now - datetime.fromisoformat(observed)).total_seconds()
    return "FRESH" if connected and 0 <= age <= seconds else "CACHED"


class OptionsFeedState:
    MAX_SUBSCRIPTIONS = 2048

    def __init__(self):
        self.lock = threading.RLock()
        self.requested = False
        self.chains: dict[str, dict] = {}
        self.contracts: dict[str, list[dict]] = {}
        self.pending: set[str] = set()
        self.watched: set[str] = set()
        self.quotes: dict[str, dict] = {}
        self.errors: dict[str, str] = {}
        self.catalog_error: str | None = None
        self.catalog_timestamp: str | None = None
        self._next_discovery = 0.0
        self._retry_at: dict[str, float] = {}
        self._entities: dict[str, Any] = {}
        self.contract_index = {}
        self.live = OptionsLiveState()

    def reset_session(self):
        # Preserve observed snapshots but rebuild provider subscriptions after reconnect.
        with self.lock:
            self._entities = {}
            self.pending.update(self.watched)
            self._retry_at.clear()
            self._next_discovery = 0
        self.live.reset()

    def _discover(self, api):
        symbols = [s for s in api.query_quotes(ins_class="OPTION", expired=False)
                   if s.split(".", 1)[0] in EXCHANGES]
        symbol_set = set(symbols)
        rows = []
        for offset in range(0, len(symbols), 1000):
            rows.extend(api.query_symbol_info(symbols[offset:offset + 1000]).to_dict("records"))
        underlying_ids = sorted({r.get("underlying_symbol") for r in rows
                                 if isinstance(r.get("underlying_symbol"), str) and r["underlying_symbol"]})
        underlying_types = {}
        for offset in range(0, len(underlying_ids), 1000):
            for r in api.query_symbol_info(underlying_ids[offset:offset + 1000]).to_dict("records"):
                underlying_types[r["instrument_id"]] = r.get("ins_class")
        chains, contracts = {}, {}
        for r in rows:
            symbol, underlying = r.get("instrument_id"), r.get("underlying_symbol")
            expiry = timestamp(r.get("expire_datetime"))
            strike = number(r.get("strike_price"), positive=True)
            kind = r.get("option_class")
            if (symbol not in symbol_set or not expiry or not strike or kind not in ("CALL", "PUT")
                    or underlying_types.get(underlying) not in ("FUTURE", "INDEX")):
                continue
            exchange = symbol.split(".", 1)[0]
            chain_id = f"{exchange}:{underlying}:{expiry}"
            chains.setdefault(chain_id, {
                "id": chain_id, "exchange": exchange, "underlyingSymbol": underlying,
                "underlyingType": underlying_types[underlying], "expiry": expiry,
                "product": str(r.get("product_id") or symbol.split(".", 1)[1].split("-")[0]),
            })
            contracts.setdefault(chain_id, []).append({
                "symbol": symbol, "name": str(r.get("instrument_name") or symbol),
                "optionClass": kind, "strike": strike, "expiry": expiry,
                "exerciseType": r.get("exercise_type") if r.get("exercise_type") in ("A", "E") else None,
                "volumeMultiple": number(r.get("volume_multiple"), positive=True),
                "priceTick": number(r.get("price_tick"), positive=True),
            })
        for key, chain in chains.items():
            contracts[key].sort(key=lambda r: (r["strike"], r["optionClass"], r["symbol"]))
            chain["contractCount"] = len(contracts[key])
        if not chains:
            raise ValueError("No supported domestic option contracts in provider metadata")
        with self.lock:
            self.chains, self.contracts = chains, contracts
            self.contract_index = {r['symbol']: {**r, 'chainId': key, 'underlyingSymbol': chains[key]['underlyingSymbol']}
                                   for key, values in contracts.items() for r in values}
            self.pending.update(self.watched.intersection(chains))
            self.catalog_timestamp = datetime.now(timezone.utc).isoformat()
            self.catalog_error = None

    def poll(self, api):
        """Called only from TqSdkRealtimeFeed._run_session; failure never drops futures."""
        with self.lock:
            requested = self.requested
        if not requested:
            return
        if time.monotonic() >= self._next_discovery:
            self._next_discovery = time.monotonic() + 60
            try:
                self._discover(api)
                self._next_discovery = time.monotonic() + 6 * 3600
            except Exception as error:
                logger.warning("options_catalog_unavailable error_type=%s", type(error).__name__)
                with self.lock:
                    self.catalog_error = "期权目录获取失败，请检查天勤连接及数据权限；稍后自动重试。"
        with self.lock:
            pending = sorted(self.pending)
        for key in pending:
            if time.monotonic() < self._retry_at.get(key, 0):
                continue
            with self.lock:
                rows = copy.deepcopy(self.contracts.get(key, []))
                chain = self.chains.get(key)
            if not chain:
                continue
            ids = [chain["underlyingSymbol"], *[r["symbol"] for r in rows]]
            missing = [s for s in ids if s not in self._entities]
            if len(self._entities) + len(missing) > self.MAX_SUBSCRIPTIONS:
                with self.lock:
                    self.errors[key] = "本连接期权订阅容量已满，重启行情服务后可选择新的期权链。"
                    self.pending.discard(key)
                continue
            try:
                if missing:
                    entities = api.get_quote_list(missing)
                    self._entities.update(zip(missing, entities, strict=True))
                with self.lock:
                    self.pending.discard(key)
                    self.errors.pop(key, None)
            except Exception as error:
                logger.warning("options_chain_unavailable error_type=%s", type(error).__name__)
                self._retry_at[key] = time.monotonic() + 60
                with self.lock:
                    self.errors[key] = "期权报价订阅失败，请检查数据权限；稍后自动重试。"
        # Keep quote timestamps supplied by the exchange, including during closed sessions.
        updates = {}
        for symbol, entity in self._entities.items():
            try:
                updates[symbol] = quote_snapshot(entity)
            except Exception as error:
                logger.warning("options_quote_unavailable error_type=%s", type(error).__name__)
        with self.lock:
            self.quotes.update(updates)

    def catalog_snapshot(self, connected: bool, configured: bool) -> dict:
        with self.lock:
            self.requested = True
            chains = copy.deepcopy(sorted(self.chains.values(), key=lambda r: (r["exchange"], r["underlyingSymbol"], r["expiry"])))
            status = ("FRESH" if connected else "CACHED") if self.catalog_timestamp else ("WARMING" if configured else "UNAVAILABLE")
            if self.catalog_error:
                status = "CACHED" if self.catalog_timestamp else "UNAVAILABLE"
            return {"source": SOURCE, "dataStatus": status, "dataTimestamp": self.catalog_timestamp,
                    "message": self.catalog_error or ("" if chains else "等待天勤期权目录；需配置具有期权数据权限的天勤账户。"), "chains": chains}

    def live_contract(self, symbol):
        with self.lock:
            self.requested = True
            metadata = copy.deepcopy(self.contract_index.get(symbol))
        if metadata is None:
            raise ValueError('期权合约不在真实目录中，请刷新期权链后选择。')
        if datetime.fromisoformat(metadata['expiry']) <= datetime.now(timezone.utc):
            raise ValueError('期权合约已到期。')
        self.live.request(symbol)
        return metadata

    def live_mappings(self):
        with self.live.lock:
            return {s: s for s in self.live.requested}

    def chain_snapshot(self, chain_id: str, connected: bool, freshness_seconds: float) -> dict:
        with self.lock:
            if chain_id not in self.chains:
                raise KeyError(chain_id)
            if chain_id not in self.watched:
                self.watched.add(chain_id)
                self.pending.add(chain_id)
            rows = copy.deepcopy(self.contracts[chain_id])
            chain = dict(self.chains[chain_id])
            quotes = copy.deepcopy(self.quotes)
            message = self.errors.get(chain_id, "")
            waiting = chain_id in self.pending
        now = datetime.now(timezone.utc)
        underlying = quotes.get(chain["underlyingSymbol"], {})
        underlying = {**underlying, "dataStatus": freshness(underlying.get("dataTimestamp"), connected, freshness_seconds, now)}
        result = []
        for row in rows:
            q = quotes.get(row["symbol"], {})
            result.append({**row, **q, "exerciseType": q.get("exerciseType") or row["exerciseType"],
                           "dataStatus": freshness(q.get("dataTimestamp"), connected, freshness_seconds, now)})
        states = [r["dataStatus"] for r in result] + [underlying["dataStatus"]]
        status = "FRESH" if all(s == "FRESH" for s in states) else "CACHED"
        if all(s == "UNAVAILABLE" for s in states):
            status = "WARMING" if waiting and not message else "UNAVAILABLE"
        return {"chain": chain, "underlying": underlying, "contracts": result, "source": SOURCE,
                "dataStatus": status, "message": message or ("正在订阅期权链，稍后自动刷新。" if waiting else ""),
                "retrievedAt": now.isoformat()}
