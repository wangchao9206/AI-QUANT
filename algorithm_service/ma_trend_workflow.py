"""Read-only preview of daily MA triggers and next-session 15-minute indicators."""

from datetime import date, timedelta
import json
import logging
import os
from pathlib import Path
from threading import BoundedSemaphore
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from algorithm_service.personal_trinity import ARCHIVE_NAME
from backtesting.personal_ma_signals import ma_tape
from scripts.research_personal_ma_multiframe import HISTORY, MULTI_WINDOW, validated_sdk_inputs


logger = logging.getLogger(__name__)
BAR_SIZE = timedelta(minutes=15)
SIDES = {'LONG_CROSS': 1, 'SHORT_CROSS': -1, 'LONG_REENTRY': 1}


class PreviewRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    symbol: Literal['FG701', 'SA701', 'AP701', 'CJ701']
    signalDate: date | None = None


def _side(a, b):
    return (a > b) - (a < b) if b is not None else 0


def _dkx(bars):
    mids = [(3 * bar.close + bar.open + bar.high + bar.low) / 6 for bar in bars]
    values = []
    for index in range(len(mids)):
        main = (sum((20 - back) * mids[index - back] for back in range(20)) / 210
                if index >= 19 else None)
        average = (sum(item[0] for item in values[-9:]) + main) / 10 if index >= 28 else None
        values.append((main, average))
    return values


def _minute_indicators(bars):
    closes = [bar.close for bar in bars]
    dkx = _dkx(bars)
    fast = slow = closes[0]
    dea = 0.0
    previous = 0.0
    for index, bar in enumerate(bars):
        fast += (bar.close - fast) * 2 / 13
        slow += (bar.close - slow) * 2 / 27
        dif = fast - slow
        dea += (dif - dea) * 2 / 10
        spread = dif - dea
        ma20 = sum(closes[index - 19:index + 1]) / 20 if index >= 19 else None
        # The archive carries a much longer prefix; withhold MACD during the initial warm-up.
        warm = index >= 34
        cross = None
        if index >= 35:
            if spread > 0 >= previous:
                cross = 'GOLD'
            elif spread < 0 <= previous:
                cross = 'DEATH'
        previous = spread
        yield {'at': (bar.timestamp + BAR_SIZE).isoformat(), 'close': bar.close, 'ma20': ma20,
               'trend': _side(bar.close, ma20), 'dif': dif if warm else None,
               'dea': dea if warm else None, 'macdCross': cross, 'dkx': dkx[index][0], 'madkx': dkx[index][1]}


def _daily_indicators(bars):
    for bar, ma, (dkx, madkx) in zip(bars, ma_tape(bars), _dkx(bars), strict=True):
        trend = _side(bar.close, ma['ma20'])
        strong = trend if trend == _side(bar.close, ma['ma5']) else 0
        trigger = ma['trigger']
        if trigger == 'LONG_REENTRY' and trend != 1:
            trigger = None
        yield bar.timestamp.date(), {'close': bar.close, 'ma5': ma['ma5'], 'ma10': ma['ma10'],
                                     'ma20': ma['ma20'], 'trend': trend, 'strong': strong,
                                     'trigger': trigger, 'dkx': dkx, 'madkx': madkx}


def preview(request: PreviewRequest, history: Path):
    try:
        archive = json.loads((history / ARCHIVE_NAME).read_bytes())
        minutes, minute_dates, _, daily, _, _ = validated_sdk_inputs(archive, request.symbol, MULTI_WINDOW, history=history)
        daily_by_date = dict(_daily_indicators(daily))
        traded = list(dict.fromkeys(minute_dates))
        successors = {day: next_day for day, next_day in zip(traded, traded[1:])
                      if day >= MULTI_WINDOW[0] and day in daily_by_date}
        if not successors:
            raise ValueError('No complete pair of trading days')
    except (OSError, ValueError, KeyError, TypeError, OverflowError) as exc:
        logger.warning('Could not verify MA workflow archive for %s', request.symbol, exc_info=True)
        raise HTTPException(503, detail='暂时无法读取已核验的日线与 15 分钟行情') from exc
    days = list(successors)
    selected = request.signalDate or next((day for day in reversed(days) if daily_by_date[day]['trigger']), days[-1])
    if selected not in successors:
        raise HTTPException(422, detail='请选择有下一交易日完整 15 分钟行情的信号日期')
    execution = successors[selected]
    # Keep only the causal prefix. Night bars already carry their exchange trading date.
    end = next((i for i, day in enumerate(minute_dates) if day > execution), len(minute_dates))
    side = SIDES.get(daily_by_date[selected]['trigger'], 0)
    rows = [row for day, row in zip(minute_dates[:end], _minute_indicators(minutes[:end]), strict=True)
            if day == execution]
    for row in rows:
        row['confirmed'] = bool(side and row['trend'] == side)
    return {'symbol': request.symbol, 'scope': {'first': days[0], 'last': days[-1]},
            'signalDate': selected, 'executionDate': execution, 'daily': daily_by_date[selected],
            'confirmedAt': next((row['at'] for row in rows if row['confirmed']), None), 'minutes': rows}


def router_for(capacity: BoundedSemaphore):
    router = APIRouter(prefix='/api/v1/research/ma-trend-workflow')

    @router.post('/preview')
    def run(request: PreviewRequest):
        if not capacity.acquire(blocking=False):
            raise HTTPException(429, detail='历史试算正在运行，请稍后重试')
        try:
            return preview(request, Path(os.environ.get('HISTORY_CACHE_DIR', str(HISTORY))))
        finally:
            capacity.release()

    return router
