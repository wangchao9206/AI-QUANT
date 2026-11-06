"""Secret-protected monitor validation and evaluation; definitions/history live in market-service."""
import hmac
import json
import os
import re
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Literal
from algorithm_service.monitor_rules import RULES, ALGORITHM_VERSION, evaluate


class Parameters(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    rules:list[str]=Field(default_factory=lambda:list(RULES),min_length=1,max_length=30)
    maPeriods:list[int]=Field(default_factory=lambda:[5,10,20,60,180],max_length=5)
    lookback:int=Field(20,ge=5,le=120)
    volumeMultiple:float=Field(2,ge=1,le=100)
    jumpPct:float=Field(10,ge=.1,le=1000)
    bigLots:int=Field(100,ge=1,le=1000000)
    bollStd:float=Field(2,ge=.5,le=10)
    atrMultiple:float=Field(2,ge=.5,le=20)
    cooldownSeconds:int=Field(60,ge=10,le=3600)
    pivotBars:int=Field(2,ge=1,le=5)

    @field_validator('rules')
    @classmethod
    def valid_rules(cls,values):
        if len(set(values))!=len(values) or any(v not in RULES for v in values):raise ValueError('Unknown or duplicate monitor rule')
        return values

    @field_validator('maPeriods')
    @classmethod
    def valid_ma(cls,values):
        if len(set(values))!=len(values) or any(v not in (5,10,20,60,180) for v in values):raise ValueError('Unsupported MA period')
        return sorted(values)


class Spec(BaseModel):
    model_config=ConfigDict(extra='forbid')
    assetType:Literal['FUTURE','OPTION']
    symbol:str=Field(min_length=2,max_length=100)
    seconds:int=60
    parameters:Parameters=Field(default_factory=Parameters)

    @field_validator('seconds')
    @classmethod
    def valid_seconds(cls,value):
        if value not in (60,180,300,900):raise ValueError('Monitor bars must be 1/3/5/15 minutes')
        return value


class Evaluation(BaseModel):
    model_config=ConfigDict(extra='forbid')
    spec:Spec
    state:dict=Field(default_factory=dict)


def router_for(feed):
    def internal(x_identity_service_secret:str=Header(default='')):
        expected=os.getenv('IDENTITY_INTERNAL_SECRET','')
        if len(expected)<32 or not hmac.compare_digest(expected,x_identity_service_secret):raise HTTPException(403,'Forbidden')
    router=APIRouter(prefix='/internal/v1/monitor',dependencies=[Depends(internal)])

    def resolve(spec):
        if spec.assetType=='OPTION':
            options=getattr(feed,'options',None)
            if options is None:raise ValueError('主源期权行情不可用。')
            options.catalog_snapshot(feed.connected,feed.configured)
            metadata=options.live_contract(spec.symbol)
            return spec.model_copy(update={'symbol':metadata['symbol']}),metadata
        from data.tqsdk_feed import canonical_symbol
        symbol=spec.symbol.strip().upper()
        provider=feed.provider_symbol(symbol)
        if not provider:raise ValueError('期货合约不在主源真实目录中。')
        canonical=canonical_symbol(provider)
        with feed.lock:
            quote=dict(feed.quotes.get(canonical,{}))
            providers=dict(feed.provider_symbols)
        resolved=quote.get('underlyingSymbol') or canonical
        if not re.fullmatch(r'[A-Z]{1,4}[0-9]{3,4}',resolved) or resolved not in providers:
            raise ValueError('尚未取得实际交割合约，等待主源元数据后重试。')
        return spec.model_copy(update={'symbol':resolved}),{'requestedSymbol':symbol,'symbol':resolved,'name':quote.get('displayName',resolved)}

    @router.get('/catalog')
    async def catalog():
        return {'algorithmVersion':ALGORITHM_VERSION,'rules':[{'code':k,'label':v} for k,v in RULES.items()],
                'defaults':Parameters().model_dump(),'frequencies':[60,180,300,900],
                'maxEnabledPerTenant':20,'maxEnabledGlobal':32}

    @router.post('/validate')
    async def validate(spec:Spec):
        try:
            normalized,metadata=await run_in_threadpool(resolve,spec)
            return {'spec':normalized.model_dump(),'metadata':metadata}
        except (ValueError,AttributeError) as error:raise HTTPException(400,str(error)) from error

    @router.post('/evaluate')
    async def run(body:Evaluation):
        if len(json.dumps(body.state))>131072:raise HTTPException(400,'Monitor state too large')
        def read():
            spec=body.spec
            if spec.assetType=='OPTION':
                depth=feed.option_depth_snapshot(spec.symbol)
                chart=feed.option_chart_snapshot(spec.symbol,spec.seconds,600)
            else:
                depth=feed.microstructure_snapshot(spec.symbol)
                chart=feed.intraday_snapshot(spec.symbol,spec.seconds,600)
            if depth.get('symbol')!=spec.symbol or chart.get('symbol')!=spec.symbol:
                raise ValueError('行情与所选监控合约不一致。')
            return evaluate({'depth':depth,'chart':chart},body.state,spec.parameters.model_dump(),spec.seconds)
        try:return await run_in_threadpool(read)
        except (ValueError,AttributeError,KeyError) as error:
            return {'status':'EXPIRED' if '已到期' in str(error) else 'WARMING','message':str(error),'state':body.state,'events':[],
                    'sourceTimestamp':None,'metrics':{},'algorithmVersion':ALGORITHM_VERSION}
    return router
