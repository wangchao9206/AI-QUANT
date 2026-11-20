from datetime import datetime, timedelta

from algorithm_service.ma_trend_workflow import PreviewRequest, _dkx, _minute_indicators, preview
from data.data_feed import KLineBar
from data.trading_day import SHANGHAI
from scripts.research_personal_ma_multiframe import HISTORY


def test_dkx_and_macd_remain_causal_when_new_bars_arrive():
    start = datetime(2026, 11, 2, 9, tzinfo=SHANGHAI)
    bars = [KLineBar(start + timedelta(minutes=15 * i), value, value, value, value, 1, 0, 'FG701')
            for i, value in enumerate([100 + i for i in range(45)] + [200 - i * 2 for i in range(20)])]
    initial = list(_minute_indicators(bars[:50]))
    assert list(_minute_indicators(bars))[:50] == initial
    assert _dkx(bars[:19])[-1] == (None, None)
    assert _dkx(bars[:20])[-1][0] == sum((20 - i) * (119 - i) for i in range(20)) / 210
    assert initial[0]['at'] == (start + timedelta(minutes=15)).isoformat()


def test_verified_archive_uses_following_exchange_session_and_first_closed_confirmation():
    result = preview(PreviewRequest(symbol='FG701'), HISTORY)
    assert result['daily']['trigger']
    assert result['signalDate'] < result['executionDate']
    assert result['scope']['first'] <= result['signalDate'] <= result['scope']['last']
    signals = [row for row in result['minutes'] if row['confirmed']]
    assert result['confirmedAt'] == (signals[0]['at'] if signals else None)
    assert all(row['trend'] == (row['close'] > row['ma20']) - (row['close'] < row['ma20']) for row in result['minutes'])
    assert all(datetime.fromisoformat(row['at']).minute % 15 == 0 for row in result['minutes'])
    assert result == preview(PreviewRequest(symbol='FG701', signalDate=result['signalDate']), HISTORY)
