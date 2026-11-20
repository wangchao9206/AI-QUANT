from datetime import datetime, timedelta
import json

import pytest
from pydantic import ValidationError

from algorithm_service.paper_strategy import StrategyRequest, evaluate
from algorithm_service.personal_trinity import ARCHIVE_NAME, HISTORY, MULTI_WINDOW, validated_sdk_inputs


RULES = dict(fastPeriod=5, mediumPeriod=10, slowPeriod=20, convergenceDays=3,
             entryMinutes=15, confirmation='either', addMode='MINUTE_ADD', waitTradingDays=10)


@pytest.fixture(scope='module')
def archive():
    path = HISTORY / ARCHIVE_NAME
    if not path.is_file():
        pytest.skip('verified delivery-contract archive is not installed')
    return validated_sdk_inputs(json.loads(path.read_bytes()), 'FG701', MULTI_WINDOW)


def wire(bar):
    return dict(timestamp=bar.timestamp, open=bar.open, high=bar.high, low=bar.low,
                close=bar.close, volume=bar.volume, contract=bar.contract_symbol)


def request(archive, value, trading_day, **overrides):
    minute, dates, sessions, daily, _, _ = archive
    as_of = datetime.fromisoformat(value)
    rows = [(wire(bar), day) for bar, day in zip(minute, dates) if bar.timestamp <= as_of]
    return StrategyRequest(**{
        'strategy': 'PERSONAL_TRINITY', 'symbol': 'FG701', 'asOf': as_of,
        # Include the future daily close and forming minute to ensure neither can leak.
        'bars': [wire(bar) for bar in daily], 'minuteBars': [row for row, _ in rows],
        'minuteTradingDates': [day for _, day in rows], 'tradingSessions': sessions,
        'tradingDate': trading_day, 'minuteCadence': 15, 'trinity': RULES,
        'startedAt': '2026-09-10T09:00:00+08:00', **overrides,
    })


def test_reopens_after_session_break_then_waits_for_next_short_signal(archive):
    result = evaluate(request(archive, '2026-09-17T10:30:15+08:00', '2026-09-17'))
    assert result['signal'] == 'SELL'
    assert result['signalTime'].isoformat() == '2026-09-17T10:15:00+08:00'
    same_setup = evaluate(request(archive, '2026-09-17T10:30:15+08:00', '2026-09-17',
                                  lastEntrySignalTime=result['signalTime']))
    expired = evaluate(request(archive, '2026-09-17T10:32:01+08:00', '2026-09-17'))
    assert same_setup['signal'] == expired['signal'] == 'HOLD'


def test_daily_reversal_flattens_without_minutes_or_using_future_bars(archive):
    observed = ('2026-11-02T21:00:10+08:00', '2026-11-03')
    rejected = evaluate(request(archive, *observed, direction=-1, positionLots=1,
                                minuteBars=[], minuteTradingDates=[]))
    assert rejected['signal'] == 'FLATTEN'
    assert rejected['signalTime'].isoformat() == '2026-11-02T15:00:00+08:00'
    earlier = evaluate(request(archive, '2026-11-02T14:59:59+08:00', '2026-11-02',
                               direction=-1, positionLots=1, minuteBars=[], minuteTradingDates=[]))
    assert earlier['signal'] == 'WARMING'


def test_new_night_session_confirmation_entry_and_add_follow_actual_position(archive):
    opened = evaluate(request(archive, '2026-11-04T22:00:10+08:00', '2026-11-05'))
    assert opened['signal'] == 'BUY'
    assert opened['modelVersion'] == 'paper-personal-trinity-v1'
    kwargs = dict(direction=1, positionLots=1,
                  positionOpenedAt=opened['signalTime'] + timedelta(seconds=10))
    observed = ('2026-11-12T21:30:10+08:00', '2026-11-13')
    add = evaluate(request(archive, *observed, **kwargs))
    assert add['signal'] == 'ADD_LONG'
    assert add['signalTime'].isoformat() == '2026-11-12T21:30:00+08:00'
    duplicate = evaluate(request(archive, *observed, **kwargs, lastSignalTime=add['signalTime']))
    no_add = evaluate(request(archive, *observed, **kwargs, trinity={**RULES, 'addMode': 'NONE'}))
    too_new = evaluate(request(archive, *observed, **kwargs, startedAt=add['signalTime']))
    full = evaluate(request(archive, *observed, **{**kwargs, 'positionLots': 2}))
    assert duplicate['signal'] == no_add['signal'] == too_new['signal'] == full['signal'] == 'HOLD'


def test_rejects_missing_exchange_dates_and_mismatched_position(archive):
    args = (archive, '2026-11-04T22:00:10+08:00', '2026-11-05')
    with pytest.raises(ValidationError, match='交易日'):
        request(*args, minuteTradingDates=[])
    with pytest.raises(ValidationError, match='持仓方向'):
        request(*args, direction=1)
