"""Selected-configuration replay of the verified daily and minute research archive."""

from hashlib import sha256
import json
import logging
import os
from pathlib import Path
from threading import BoundedSemaphore
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backtesting.personal_ma_multiframe_execution import run_multiframe_account
from backtesting.personal_ma_multiframe_signals import minute_events
from backtesting.personal_ma_signals import ma_tape
from scripts.research_personal_ma_multiframe import HISTORY, MULTI_WINDOW, validated_sdk_inputs


ARCHIVE_NAME = 'personal-ma-multiframe-2026-11-19.tqsdk.json'
logger = logging.getLogger(__name__)


class TrinityRules(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

    fastPeriod: int = Field(ge=2, le=120)
    mediumPeriod: int = Field(ge=2, le=120)
    slowPeriod: int = Field(ge=2, le=120)
    convergenceDays: int = Field(ge=2, le=20)
    entryMinutes: Literal[15, 30, 60]
    confirmation: Literal['chan', 'wyckoff', 'either']
    addMode: Literal['MINUTE_ADD', 'MA10_ADD', 'NONE']
    waitTradingDays: int = Field(ge=1, le=40)
    @field_validator('entryMinutes', mode='before')
    @classmethod
    def integer_option(cls, value):
        if type(value) is not int:
            raise ValueError('请选择整数选项')
        return value

    @model_validator(mode='after')
    def ordered_periods(self):
        if not self.fastPeriod < self.mediumPeriod < self.slowPeriod:
            raise ValueError('三条日线均线周期必须依次递增')
        return self


class BacktestRequest(TrinityRules):
    symbol: Literal['FG701', 'SA701', 'AP701', 'CJ701']
    costMultiplier: Literal[1, 2]

    @field_validator('costMultiplier', mode='before')
    @classmethod
    def integer_cost(cls, value):
        return cls.integer_option(value)


def backtest(request: BacktestRequest, history: Path):
    archive = history / ARCHIVE_NAME
    try:
        raw = archive.read_bytes()
        source = json.loads(raw)
        minutes, trade_days, sessions, daily, spec, _ = validated_sdk_inputs(
            source, request.symbol, MULTI_WINDOW, history=history,
        )
    except FileNotFoundError as exc:
        raise HTTPException(503, detail='该策略的已核验分钟行情档案尚未就绪') from exc
    except (OSError, ValueError, KeyError, TypeError, OverflowError) as exc:
        logger.warning('Personal Trinity archive could not be verified for %s', request.symbol, exc_info=True)
        raise HTTPException(503, detail='该策略的历史行情档案未通过完整性核验') from exc

    start, end = MULTI_WINDOW
    periods = (request.fastPeriod, request.mediumPeriod, request.slowPeriod)
    tape = ma_tape(daily, periods=periods, convergence_days=request.convergenceDays)
    daily_signals = {row.timestamp.date(): signal for row, signal in zip(daily, tape, strict=True)}
    events = minute_events(minutes, trade_days, sessions, 15, periods=(request.entryMinutes,))
    confirmations = events[request.entryMinutes][request.confirmation]
    result = run_multiframe_account(
        minutes, trade_days, daily_signals, spec, start, end,
        confirmations=confirmations, no_add=request.addMode == 'NONE',
        minute_add=request.addMode == 'MINUTE_ADD', cost_multiplier=request.costMultiplier,
        wait_days=request.waitTradingDays,
    )
    return {
        'symbol': request.symbol,
        'scope': {'first': start.isoformat(), 'last': end.isoformat(),
                  'scoreDays': len({day for day in trade_days if start <= day <= end})},
        'configuration': request.model_dump(),
        'sourceSha256': sha256(raw).hexdigest(),
        'metrics': result['metrics'],
        'trades': result['trades'],
    }


def router_for(capacity: BoundedSemaphore) -> APIRouter:
    router = APIRouter(prefix='/api/v1/research/personal-trinity', tags=['Personal Trinity'])

    @router.post('/backtest')
    def run(request: BacktestRequest):
        if not capacity.acquire(blocking=False):
            raise HTTPException(429, detail='历史回测正在运行，请稍后重试')
        try:
            history = Path(os.environ.get('HISTORY_CACHE_DIR', str(HISTORY)))
            return backtest(request, history)
        finally:
            capacity.release()

    return router
