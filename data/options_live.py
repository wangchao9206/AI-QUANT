"""Bounded options depth/ticks; SDK entities are owned by the existing feed worker."""
import copy
import threading
import time
from datetime import datetime, timezone


class OptionsLiveState:
    MAX_SUBSCRIPTIONS = 32

    def __init__(self):
        self.lock = threading.RLock()
        self.requested = set()
        self.snapshots = {}
        self.errors = {}
        self.ticks = {}
        self.retry = {}

    def request(self, symbol):
        with self.lock:
            if symbol not in self.requested and len(self.requested) >= self.MAX_SUBSCRIPTIONS:
                raise ValueError('实时期权盘口已达到 32 个合约上限，请复用已有订阅。')
            self.requested.add(symbol)

    def reset(self):
        self.ticks.clear()
        self.retry.clear()

    def _capture(self, symbol, entity):
        from data.tqsdk_feed import quote_to_microstructure, ticks_to_trades
        from data.options_feed import timestamp
        observed=timestamp(entity.get('datetime') if isinstance(entity,dict) else getattr(entity,'datetime',None))
        if observed is None:
            raise ValueError('Option source timestamp is unavailable')
        snapshot = quote_to_microstructure(symbol, entity, ticks_to_trades(self.ticks[symbol].copy(), 200))
        if snapshot['lastPrice'] is None and not any(r['price'] is not None for r in snapshot['bids']+snapshot['asks']):
            raise ValueError('Option depth is unavailable')
        snapshot['dataTimestamp']=observed
        snapshot['source'] = '天勤 TqSdk 期权盘口'
        with self.lock:
            self.snapshots[symbol] = snapshot
            self.errors.pop(symbol, None)

    def subscribe(self, api, quote_entities, capacity):
        with self.lock:
            requested = sorted(self.requested)
        for symbol in requested:
            if symbol in self.ticks or time.monotonic() < self.retry.get(symbol, 0):
                continue
            try:
                if symbol not in quote_entities:
                    if len(quote_entities) >= capacity:
                        raise ValueError('Option quote capacity reached')
                    quote_entities[symbol] = api.get_quote_list([symbol])[0]
                self.ticks[symbol] = api.get_tick_serial(symbol, data_length=1000)
                self._capture(symbol, quote_entities[symbol])
            except Exception:
                self.ticks.pop(symbol, None)
                self.retry[symbol] = time.monotonic() + 30
                with self.lock:
                    self.errors[symbol] = '期权盘口订阅暂不可用，检查权限或等待重试。'
            break

    def update(self, api, quote_entities):
        for symbol, serial in list(self.ticks.items()):
            entity = quote_entities.get(symbol)
            if entity is not None and (api.is_changing(entity) or api.is_changing(serial)):
                try:self._capture(symbol, entity)
                except (ValueError,TypeError,OverflowError):
                    with self.lock:self.errors[symbol]='期权源时点或盘口字段缺失，保留旧快照等待恢复。'

    def snapshot(self, symbol, connected, freshness):
        with self.lock:
            result = copy.deepcopy(self.snapshots.get(symbol))
            error = self.errors.get(symbol)
        if not result:
            raise ValueError(error or '正在订阅真实期权盘口，请稍后重试。')
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(result['dataTimestamp'])).total_seconds()
        result['dataStatus'] = 'FRESH' if connected and not error and 0 <= age <= freshness else 'CACHED'
        result['message'] = error or ''
        return result
