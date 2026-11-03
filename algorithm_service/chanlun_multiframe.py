"""Immutable, same-cutoff reconstruction from independent primary serials."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import threading
from typing import Literal
from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from data.chanlun_monitor_source import FREQUENCIES, primary_snapshot
from chanlun_worker.monitor import canonical, merge_closed, observe


class Request(BaseModel):
    model_config=ConfigDict(extra='forbid')
    symbol: str=Field(pattern=r'^[A-Z]{1,4}[0-9]{3,4}$')
    frames: Literal['PAIR','TRIPLE']='PAIR'
    asOf: AwareDatetime | None=None


def reconstruct(captured, symbol, cutoff, captured_at):
    """Cut input BEFORE calculation. Timestamps are conservative successor bounds,
    never claims about the historical network availability of these prices.
    """
    if cutoff>captured_at:
        raise ValueError('观察界限不能晚于实际采集时间')
    frames=[]
    for frequency, source in captured.items():
        selected=[]
        seconds=FREQUENCIES[frequency]
        for left,right in zip(source['bars'],source['bars'][1:]):
            seal=datetime.fromisoformat(right['timestamp'])
            start=datetime.fromisoformat(left['timestamp'])
            if seal<=cutoff and (frequency=='DAY' or (seal-start).total_seconds()>=seconds):
                selected.append({**left,'sealedByTimestamp':right['timestamp']})
        if len(selected)<50:
            raise ValueError(f'{frequency} 在此界限不足 50 根已封存原始 K 线，请选择较晚时点')
        bars=merge_closed([],selected,symbol)
        analysis=observe(bars,symbol,frequency)
        analysis.pop('events')
        frames.append({'frequency':frequency,'source':{k:v for k,v in source.items() if k!='bars'},'analysis':analysis,
            'sourceWindowStart':source['bars'][0]['timestamp'],'sourceWindowBars':len(source['bars']),
            'firstProviderIndex':bars[0]['providerIndex'],'lastProviderIndex':bars[-1]['providerIndex'],
            'lastSealedBy':bars[-1]['sealedByTimestamp']})
    config={'symbol':symbol,'frames':[f['frequency'] for f in frames],'asOf':cutoff.isoformat(),
            'mode':'HISTORICAL_SUCCESSOR_BOUND_RECONSTRUCTION','priceBasis':'UNADJUSTED_DELIVERY',
            'implementationHash':hashlib.sha256(Path(__file__).read_bytes().replace(b'\r\n',b'\n')).hexdigest()}
    return {'schemaVersion':1,'config':config,'configHash':hashlib.sha256(canonical(config).encode()).hexdigest(),
            'capturedAt':captured_at.isoformat(),'asOf':cutoff.isoformat(),'frames':frames,'executable':False,
            'limitations':[
                '各周期独立读取主源原始 K 线，不从日线或其他周期生成。',
                '先截取输入再计算；后一根时间戳为保守重建界限，不等于历史网络可得时间。',
                '本次来源实际接收时间另列，历史重建不属于未知样本或真实前向观察。',
                '各周期源窗口最多两千根，起点与预热长度可能不同；每次结果固定保存，不跨窗口自动匹配结构身份。',
                '日线保留 SDK 时间戳，仍待精确交易日与可得时间映射；不取得实时提醒或交易资格。',
                '十字线同步定位，不能用当前结构解释更早时点；更早观察需要重新构建。']}


def router_for(feed):
    router=APIRouter(prefix='/internal/v1/chanlun')
    gate=threading.BoundedSemaphore(1)
    def compute(request):
        if not hasattr(feed,'watch_chanlun'):
            return {'status':'WAITING_INPUT','message':'主源封存数据不可用'}
        frequencies=['DAY','MIN30','MIN5'] if request.frames=='TRIPLE' else ['MIN30','MIN5']
        captured={};missing=[]
        # This RLock protects one consistent source capture; SDK calculations
        # run after release, so quote delivery is not held during native analysis.
        with feed.lock:
            captured_at=datetime.now(timezone.utc)
            for frequency in frequencies:
                try:
                    state=primary_snapshot(feed,request.symbol,frequency,captured_at)
                except ValueError:
                    missing.append(frequency+' 主源目录或订阅容量未通过');continue
                if state['status'] not in ('READY','CLOSED'):
                    missing.append(frequency+' '+state['message']);continue
                raw=deepcopy(feed.chanlun_snapshots[(request.symbol,FREQUENCIES[frequency])])
                captured[frequency]={'bars':raw['bars'],**{k:v for k,v in state.items() if k!='bars'}}
        if missing:
            return {'status':'WAITING_INPUT','message':'；'.join(missing)}
        cutoff=request.asOf
        if cutoff is None:
            proven=[datetime.fromisoformat(b['timestamp']) for s in captured.values() for b in s['bars'][1:]
                    if datetime.fromisoformat(b['timestamp'])<=captured_at]
            cutoff=max(proven)
        return {'status':'SUCCEEDED','report':reconstruct(captured,request.symbol,cutoff,captured_at)}
    @router.post('/multiframe')
    async def run(request: Request):
        if not gate.acquire(blocking=False):raise HTTPException(429,'多周期观察计算忙，请稍后重试')
        try:return await run_in_threadpool(compute,request)
        except ValueError as error:raise HTTPException(422,str(error)) from error
        finally:gate.release()
    return router
