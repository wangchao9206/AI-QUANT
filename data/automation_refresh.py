"""Bounded, fresh SDK history downloads for explicit automation starts.

The refresh worker owns its own temporary SDK session. HTTP threads only enqueue
or inspect jobs; the shared live SDK and its subscriptions remain untouched.
"""
from __future__ import annotations
import asyncio
import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import tempfile
import threading
import time
import uuid


class AutomationRefresh:
    MAX_JOBS = 256

    def __init__(self, feed, cache_dir=None):
        self.feed = feed
        self.cache_dir = Path(cache_dir) if cache_dir is not None else Path(os.getenv('HISTORY_CACHE_DIR', 'data/history')) / 'tqsdk-automation'
        self.lock = threading.RLock()
        self.jobs = {}
        self.generation = str(uuid.uuid4())
        self.closed = threading.Event()
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='tqsdk-start-refresh')

    def request(self, contract, key):
        if not re.fullmatch(r'[A-Z]{1,4}[0-9]{3,4}', contract) or not re.fullmatch(r'[A-Za-z0-9:._-]{8,128}', key):
            raise ValueError('刷新必须指定实际合约和有效请求编号')
        with self.lock:
            previous = self.jobs.get(key)
            if previous and previous['contract'] != contract:
                raise ValueError('不能为不同合约复用刷新编号')
            if previous and (previous['state'] != 'FAILED' or time.monotonic() < previous.get('_retryAt', 0)):
                return self._public(previous)
            if self.closed.is_set():
                return dict(state='FAILED', contract=contract, requestKey=key, message='行情服务正在关闭，等待重新连接')
            if len(self.jobs) >= self.MAX_JOBS and key not in self.jobs:
                removable = next((k for k,v in self.jobs.items() if v['state'] in ('READY','FAILED')), None)
                if removable is None:
                    return dict(state='PENDING', contract=contract, requestKey=key, message='下载队列繁忙，等待再次申请')
                self.jobs.pop(removable)
            job = dict(contract=contract, requestKey=key, sourceStartupId=self.generation, state='PENDING',
                       requestedAt=datetime.now(timezone.utc).isoformat(), message='正在重新拉取实际合约日线与1分钟数据')
            self.jobs[key] = job
            self.pool.submit(self._run, key)
            return self._public(job)

    @staticmethod
    def _public(job):
        return {k:copy.deepcopy(v) for k,v in job.items() if not k.startswith('_')}

    def _run(self, key):
        with self.lock:
            job = dict(self.jobs[key])
        try:
            result = self._download(job['contract'])
            with self.lock:
                self.jobs[key] = {**job, **result, 'state':'READY', 'message':'已从天勤重新拉取并校验最新历史数据'}
        except Exception as error:
            with self.lock:
                self.jobs[key] = {**job, 'state':'FAILED', '_retryAt':time.monotonic()+15,
                                  'message':'最新数据拉取或校验失败，等待重试；未使用旧缓存放行', 'errorType':type(error).__name__}

    def _download(self, contract):
        from data.tqsdk_feed import canonical_symbol, quote_to_snapshot
        from data.intraday_feed import observed_bars
        from data.trading_day import completed_daily_bar, SHANGHAI
        provider = self.feed.provider_symbol(contract)
        if not self.feed.configured or not provider or canonical_symbol(provider) != contract:
            raise ValueError('实际合约或天勤认证未就绪')
        # Register ongoing primary subscriptions, without accessing their SDK entities.
        self.feed.watch(contract)
        with self.feed.lock:
            mappings = dict(self.feed.provider_symbols)
        self.feed.intraday.request(contract, 60, mappings)
        self.feed.wake_event.set()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        api = None
        task = None
        try:
            api = self.feed._new_api()
            def subscribe():
                return (api.get_quote(provider), api.get_kline_serial(provider, 86400, data_length=5000),
                        api.get_kline_serial(provider, 60, data_length=600))
            deadline = time.monotonic()+75
            def wait():
                if self.closed.is_set() or time.monotonic() >= deadline:
                    raise TimeoutError('History refresh timed out')
                api.wait_update(deadline=time.time()+1)
            if callable(getattr(api, 'create_task', None)):
                async def load():
                    return subscribe()
                task = api.create_task(load())
                while not task.done():
                    wait()
                quote_entity, daily_serial, minute_serial = task.result()
                while not api.is_serial_ready(daily_serial) or not api.is_serial_ready(minute_serial):
                    wait()
            else:
                quote_entity, daily_serial, minute_serial = subscribe()
            # A missing provider timestamp must never be replaced by the wall clock.
            raw_stamp = quote_entity.get('datetime') if isinstance(quote_entity, dict) else getattr(quote_entity, 'datetime', None)
            if not raw_stamp:
                raise ValueError('Missing actual quote timestamp')
            quote = quote_to_snapshot(contract, quote_entity)
            source_at = datetime.fromisoformat(quote['dataTimestamp'])
            now = datetime.now(timezone.utc)
            if source_at > now+timedelta(seconds=10):
                raise ValueError('Future provider quote')
            daily = observed_bars(daily_serial.copy())
            minutes = observed_bars(minute_serial.copy())
            if not daily or not minutes:
                raise ValueError('No validated history returned')
            if datetime.fromisoformat(minutes[-1]['timestamp'])+timedelta(seconds=60, milliseconds=1) < source_at:
                raise ValueError('Minute history is older than the provider quote')
            expected = self.feed.trading_date_for(source_at)
            latest_day = datetime.fromisoformat(daily[-1]['timestamp']).astimezone(SHANGHAI).date()
            if expected and latest_day < expected:
                raise ValueError('Daily history is older than the provider trading date')
            completed = [b for b in daily if completed_daily_bar(datetime.fromisoformat(b['timestamp']), now)]
            receipt = dict(source='TQSDK_FRESH_DOWNLOAD', contract=contract, providerSymbol=provider,
                completedAt=now.isoformat(), sourceQuoteTime=quote['dataTimestamp'], dailyCount=len(daily), minuteCount=len(minutes),
                latestDailyTime=daily[-1]['timestamp'], latestCompletedDailyTime=completed[-1]['timestamp'] if completed else None,
                latestMinuteTime=minutes[-1]['timestamp'])
            self._persist(contract, dict(receipt=receipt, daily=daily, minutes=minutes))
            # Publish actual observations only. The shared feed retains ownership of live quote freshness.
            with self.feed.lock:
                by_time={}
                for b in [*self.feed.histories.get(contract, []), *daily]:
                    stamp=datetime.fromisoformat(b['timestamp']).astimezone(timezone.utc).isoformat()
                    by_time[stamp]={**b, 'timestamp':stamp}
                self.feed.histories[contract] = [by_time[k] for k in sorted(by_time)][-5000:]
            self.feed.intraday._capture((contract, '60'), minute_serial)
            return receipt
        finally:
            if task is not None and not task.done():
                task.cancel()
            if api is not None:
                api.close()
            loop.close()
            asyncio.set_event_loop(None)

    def _persist(self, contract, payload):
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.cache_dir, suffix='.tmp', delete=False) as out:
                temporary = Path(out.name)
                json.dump(payload, out, ensure_ascii=False)
                out.flush()
                os.fsync(out.fileno())
            temporary.replace(self.cache_dir / (contract+'_latest.json'))
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()

    def close(self):
        self.closed.set()
        self.pool.shutdown(wait=False, cancel_futures=True)
