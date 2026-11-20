import asyncio
import copy
from datetime import date, datetime
import json
import threading
import pandas as pd
import pytest
from data.automation_refresh import AutomationRefresh
from data.intraday_feed import IntradayFeedState


def row(stamp, index=0):
    return dict(id=index, datetime=int(pd.Timestamp(stamp).timestamp()*1e9), open=900, high=902,
                low=899, close=901, volume=10, close_oi=100)


class Api:
    def __init__(self, stale=False):
        self.calls=[];self.closed=False;self.stale=stale
    def get_quote(self, provider):
        self.calls.append((threading.current_thread().name,provider))
        return dict(datetime='2026-11-18T15:00:00.000001+08:00', last_price=901)
    def get_kline_serial(self, provider, seconds, data_length):
        self.calls.append((provider,seconds,data_length))
        if seconds==86400:
            return pd.DataFrame([row(f'2026-11-{day}T00:00:00+08:00',i) for i,day in enumerate([16,17,18])])
        return pd.DataFrame([row(f'2026-11-18T14:{minute}:00+08:00',i) for i,minute in enumerate([47,48,49] if self.stale else [57,58,59])])
    def close(self): self.closed=True


class Feed:
    configured=True
    def __init__(self, factory=Api):
        self.lock=threading.RLock();self.intraday=IntradayFeedState();self.wake_event=threading.Event()
        self.provider_symbols={'FG701':'CZCE.FG701'};self.apis=[];self.factory=factory
        self.histories={'FG701':[dict(timestamp='2026-11-17T00:00:00+08:00',price=1,open=1,high=1,low=1,volume=0)]}
        self.quotes={'FG701':{'dataTimestamp':'2026-11-18T14:59:59+08:00'}}
    def provider_symbol(self, contract): return self.provider_symbols.get(contract)
    def watch(self, _): pass
    def trading_date_for(self, _): return date(2026,11,18)
    def _new_api(self):
        api=self.factory();self.apis.append(api);return api


def drain(manager): manager.pool.submit(lambda:None).result(timeout=5)


def test_each_new_start_downloads_again_while_polling_one_start_is_idempotent(tmp_path):
    feed=Feed();manager=AutomationRefresh(feed,tmp_path)
    original=copy.deepcopy(feed.quotes)
    try:
        manager.request('FG701','first-start-0001');drain(manager)
        first=manager.request('FG701','first-start-0001')
        assert first['state']=='READY'
        for _ in range(3): assert manager.request('FG701','first-start-0001')['completedAt']==first['completedAt']
        assert len(feed.apis)==1
        manager.request('FG701','second-start-0002');drain(manager)
        second=manager.request('FG701','second-start-0002')
        assert second['state']=='READY' and len(feed.apis)==2
        assert first['requestKey']!=second['requestKey']
        assert all(api.closed for api in feed.apis)
        assert all(api.calls[0][0].startswith('tqsdk-start-refresh') for api in feed.apis)
        assert second['dailyCount']==3 and second['minuteCount']==3
        assert second['latestDailyTime'].startswith('2026-11-17T16:00:00')
        assert len(feed.histories['FG701'])==3  # Same instant in UTC and +08 is deduplicated.
        assert feed.quotes==original  # Wall-clock receipt does not make an old quote fresh.
        saved=json.loads((tmp_path/'FG701_latest.json').read_text())
        assert saved['receipt']['source']=='TQSDK_FRESH_DOWNLOAD'
        assert len(saved['daily'])==3 and len(saved['minutes'])==3
    finally: manager.close()


def test_old_history_does_not_allow_a_failed_download_to_be_reported_ready(tmp_path):
    feed=Feed(lambda:Api(stale=True));manager=AutomationRefresh(feed,tmp_path)
    original=copy.deepcopy(feed.histories)
    try:
        manager.request('FG701','failed-start-0001');drain(manager)
        result=manager.request('FG701','failed-start-0001')
        assert result['state']=='FAILED'
        assert feed.histories==original and not (tmp_path/'FG701_latest.json').exists()
        assert len(feed.apis)==1
        with pytest.raises(ValueError): manager.request('RB2701','failed-start-0001')
        with pytest.raises(ValueError): manager.request('FG0','main-start-0001')
    finally: manager.close()


def test_sdk_subscriptions_and_waiting_are_owned_by_the_refresh_worker(tmp_path):
    class AsyncApi(Api):
        def __init__(self): super().__init__();self.updates=0
        def create_task(self, coroutine): return asyncio.get_event_loop().create_task(coroutine)
        def is_serial_ready(self, _): return self.updates>=2
        def wait_update(self, deadline):
            self.updates+=1;asyncio.get_event_loop().run_until_complete(asyncio.sleep(0));return True
    feed=Feed(AsyncApi);manager=AutomationRefresh(feed,tmp_path)
    try:
        manager.request('FG701','async-start-0001');drain(manager)
        assert manager.request('FG701','async-start-0001')['state']=='READY'
        assert feed.apis[0].updates>=2 and feed.apis[0].closed
    finally: manager.close()
