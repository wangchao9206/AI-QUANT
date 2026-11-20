from datetime import datetime, timedelta
from algorithm_service.paper_strategy import StrategyRequest, evaluate

AS_OF = datetime.fromisoformat('2026-11-18T10:01:00+08:00')


def bar(stamp, price):
    return dict(timestamp=stamp, contract='FG701', open=price, high=price+1,
                low=price-1, close=price, volume=100)


def request(values, trend=1, direction=0):
    daily = [bar(AS_OF.replace(hour=0, minute=0)-timedelta(days=45-i), 200+trend*i)
             for i in range(45)]
    minutes = [bar(AS_OF-timedelta(minutes=len(values)-i), value) for i, value in enumerate(values)]
    return StrategyRequest(strategy='MA20_MACD', symbol='FG701', asOf=AS_OF,
                           bars=daily, minuteBars=minutes, direction=direction, priceTick=1)


def test_daily_macd_filters_the_direction_and_ma20_requires_a_new_cross():
    assert evaluate(request([100]*20+[110]))['signal'] == 'BUY'
    assert evaluate(request([100]*20+[90], trend=-1))['signal'] == 'SELL'
    assert evaluate(request([100]*20+[110], trend=-1))['signal'] == 'HOLD'
    assert evaluate(request(list(range(100, 121))))['signal'] == 'HOLD'


def test_forming_minutes_and_the_current_daily_bar_cannot_change_the_signal():
    r = request([100]*20+[110])
    expected = evaluate(r)
    payload = r.model_dump(by_alias=True)
    payload['minuteBars'].append(bar(AS_OF-timedelta(seconds=30), 9000))
    payload['bars'].append(bar(AS_OF.replace(hour=0, minute=0), 9000))
    actual = evaluate(StrategyRequest(**payload))
    assert actual['signal'] == expected['signal'] == 'BUY'
    assert actual['signalTime'] == expected['signalTime']
    assert actual['historyCount'] == 21


def test_ma20_exit_is_independent_of_daily_filter_and_never_reverses():
    r = request([100]*20+[90], direction=1)
    assert evaluate(r)['signal'] == 'FLATTEN'
    payload = r.model_dump(by_alias=True)
    payload['bars'] = []
    assert evaluate(StrategyRequest(**payload))['signal'] == 'FLATTEN'
    assert evaluate(request([100]*20+[102], direction=-1))['signal'] == 'HOLD'
    assert evaluate(request([100]*20+[110], direction=-1))['signal'] == 'FLATTEN'


def test_missing_history_is_a_visible_warmup_instead_of_a_trade():
    r = request([100]*10+[110])
    assert evaluate(r)['signal'] == 'WARMING'
