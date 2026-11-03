"""Private bounded research endpoint; reports are persisted by chanlun-service."""
import threading
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict

router = APIRouter(prefix='/internal/v1/chanlun')
capacity = threading.BoundedSemaphore(1)


class LabRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    group: Literal['THIRD', 'ALL'] = 'THIRD'
    initialCash: Literal[100000, 500000, 1000000] = 1000000


@router.post('/lab')
async def experiment(request: LabRequest):
    if not capacity.acquire(blocking=False):
        raise HTTPException(429, '研究计算忙，请稍后重试')
    try:
        from backtesting.native_chanlun_lab import run_lab
        return await run_in_threadpool(run_lab, request.group, request.initialCash)
    except ValueError as exc:
        raise HTTPException(422, '研究输入或冻结数据校验失败') from exc
    finally:
        capacity.release()
