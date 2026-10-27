"""Workflow validation and observed-data-only signal debugging, without orders."""
from datetime import datetime, timezone
from fastapi import HTTPException
from pydantic import BaseModel, Field, field_validator
from backtesting.workflow import compile_workflow
from data.trading_day import completed_daily_bar
from algorithm_service.paper_strategy import SignalBar, StrategyRequest, evaluate


class CheckRequest(BaseModel):
    definition: dict


class DebugRequest(CheckRequest):
    symbol: str = Field(pattern=r'^[A-Za-z]{1,4}(?:0|M)$')
    asOf: datetime
    direction: int = Field(default=0,ge=-1,le=1)
    @field_validator('asOf')
    @classmethod
    def clock(cls,value):
        if value.tzinfo is None:raise ValueError('观察时点必须包含时区')
        if value>datetime.now(timezone.utc):raise ValueError('不能以未来时点试算工作流')
        return value


def check(definition):
    try:return compile_workflow(definition).metadata()
    except ValueError as exc:raise HTTPException(422,'工作流无效：'+str(exc)[:600]) from exc


def debug(request:DebugRequest,provider,symbol):
    check(request.definition)
    dataset=provider.cached_replay(symbol)
    if dataset is None:raise HTTPException(503,'该品种暂无可核验的历史日线，未使用演示数据试算')
    def visible(rows):
        return [SignalBar(timestamp=b.timestamp,open=b.open,high=b.high,low=b.low,close=b.close,
            volume=b.volume,openInterest=b.open_interest,contract=b.contract_symbol) for b in rows
            if b.timestamp<=request.asOf and completed_daily_bar(b.timestamp,request.asOf)][-5000:]
    signals=visible(getattr(dataset,'signal_bars',None) or dataset.bars)
    execution=visible(dataset.bars)
    result=evaluate(StrategyRequest(strategy='WORKFLOW',symbol=symbol,asOf=request.asOf,bars=signals,
        executionBars=execution,direction=request.direction,workflow=request.definition))
    return {**result,'source':dataset.source,'asOf':request.asOf,'executionMode':'SIGNAL_ONLY',
            'message':'逐节点计算已知日线条件；本次试算不创建账户或订单。'}
