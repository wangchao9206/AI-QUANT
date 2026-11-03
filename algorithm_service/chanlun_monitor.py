"""Private primary-data monitor computation; Java owns leases and persistence."""
import threading
from typing import Literal
from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field

from data.chanlun_monitor_source import primary_snapshot
from chanlun_worker.monitor import InputConflict, merge_closed, observe, profile_for


class MonitorRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    symbol: str = Field(pattern=r'^[A-Z]{1,4}[0-9]{3,4}$')
    frequency: Literal['DAY','MIN5','MIN30']
    previousBars: list[dict] = Field(default_factory=list, max_length=10000)
    previousProfileHash: str | None = None


def router_for(feed):
    router = APIRouter(prefix='/internal/v1/chanlun')
    gate = threading.BoundedSemaphore(1)

    def compute(request):
        if not hasattr(feed, 'watch_chanlun'):
            return {'status':'WAITING_DATA','message':'当前行情提供器不支持主源封存监控'}
        try:
            source = primary_snapshot(feed, request.symbol, request.frequency)
        except ValueError:
            return {'status':'WAITING_DATA','message':'合约目录尚未可用或订阅容量已满，请检查主源状态'}
        if source['status'] not in ('READY','CLOSED'):
            return {'status':source['status'],'message':source['message'],'source':source}
        try:
            bars = merge_closed(request.previousBars, source['bars'], request.symbol)
            profile, profile_hash = profile_for(request.symbol, request.frequency)
            if request.previousBars and len(bars)==len(request.previousBars) and request.previousProfileHash==profile_hash:
                return {'status':source['status'],'message':source['message'],'unchanged':True,'profileHash':profile_hash,
                        'source':{k:v for k,v in source.items() if k!='bars'}}
            analysis = observe(bars, request.symbol, request.frequency)
            return {'status':source['status'],'message':source['message'],'source':{k:v for k,v in source.items() if k!='bars'},'analysis':analysis}
        except InputConflict as error:
            return {'status':error.status,'message':str(error),'source':{k:v for k,v in source.items() if k!='bars'}}

    @router.post('/monitor')
    async def poll(request: MonitorRequest):
        if not gate.acquire(blocking=False):
            raise HTTPException(429, '监控计算忙，保留原水位稍后继续')
        try:
            return await run_in_threadpool(compute, request)
        finally:
            gate.release()
    return router
