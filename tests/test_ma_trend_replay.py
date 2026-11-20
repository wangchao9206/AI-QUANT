from datetime import date, datetime, time, timedelta
from hashlib import sha256
from math import isclose
from threading import BoundedSemaphore

from fastapi import FastAPI
from fastapi.testclient import TestClient

from algorithm_service import ma_trend_replay
from algorithm_service.ma_trend_replay import ReplayRequest, replay, run_replay
from data.data_feed import KLineBar
from data.tqsdk_backtest import FuturesContractSpec
from data.trading_day import SHANGHAI
from scripts.research_personal_ma_multiframe import HISTORY


def test_shared_wallet_halves_lots_and_closes_before_reversing(monkeypatch):
    days = [date(2026, 11, 2 + i) for i in range(4)]
    signals = ('LONG_CROSS', 'LONG_REENTRY', 'SHORT_CROSS', None)
    monkeypatch.setattr(ma_trend_replay, '_daily_indicators',
                        lambda _daily: zip(days, ({'trigger': signal} for signal in signals)))
    monkeypatch.setattr(ma_trend_replay, '_minute_indicators',
                        lambda bars: ({'trend': 1 if bar.timestamp.date() < days[-1] else -1} for bar in bars))

    tape = [[(100, 100)] * 3, [(100, 100), (100, 103), (104, 104), (104, 104)],
            [(100, 100), (101, 101), (101, 101)], [(100, 100), (100, 100), (100, 100)]]
    bars = [KLineBar(datetime.combine(day, time(9), SHANGHAI) + timedelta(minutes=15 * i),
                     opening, max(opening, close), min(opening, close), close, 10_000, 0, 'FG701')
            for day, session in zip(days, tape, strict=True) for i, (opening, close) in enumerate(session)]
    request = ReplayRequest(symbol='FG701', initialCash=10_000, takeProfitPct=1, includeTimeline=True)
    result = run_replay(request, bars, [bar.timestamp.date() for bar in bars], [],
                        FuturesContractSpec('FG701', 10, 1, 200, 1), days[1], days[-1])
    opened, reduced, added, closed, short = result['executions']
    assert [row['action'] for row in result['executions']] == ['OPEN', 'TAKE_PROFIT', 'ADD', 'REVERSAL_CLOSE', 'OPEN']
    assert opened['lots'] == 23
    assert reduced['lots'] == 11
    assert added['lots'] > 0
    assert closed['lots'] == opened['lots'] - reduced['lots'] + added['lots']
    assert short['direction'] == -1 and short['at'] > closed['at']
    assert all(row['at'] >= row['signalAt'] for row in result['executions'])
    assert result['metrics']['openLots'] == short['lots']
    frames = result['reviewTimeline']
    assert frames[0]['signal'] == 'OPEN' and frames[0]['lots'] == 0 and frames[0]['executionIndexes'] == []
    assert frames[1]['executionIndexes'] == [0] and frames[1]['lots'] == opened['lots']
    assert frames[1]['signal'] == 'TAKE_PROFIT'
    assert frames[2]['executionIndexes'] == [1] and frames[2]['lots'] == opened['lots'] - reduced['lots']
    assert any(frame['signal'] == 'HOLD' for frame in frames)
    assert [index for frame in frames for index in frame['executionIndexes']] == list(range(len(result['executions'])))
    for frame in frames:
        assert frame['at'] == frame['openAt'] + ma_trend_replay.BAR_SIZE
        assert all(result['executions'][index]['at'] == frame['openAt'] for index in frame['executionIndexes'])
    assert frames[-1]['equity'] == result['metrics']['endingEquity']
    prefix = [bar for bar in bars if bar.timestamp.date() <= days[2]]
    truncated = run_replay(request, prefix, [bar.timestamp.date() for bar in prefix], [],
                           FuturesContractSpec('FG701', 10, 1, 200, 1), days[1], days[2])
    assert truncated['reviewTimeline'] == [frame for frame in frames if frame['tradingDate'] <= days[2]]


def test_review_timeline_opt_in_preserves_replay_and_identifies_verified_archive():
    request = ReplayRequest(symbol='FG701', initialCash=10_000, takeProfitPct=1)
    original = replay(request, HISTORY)
    reviewed = replay(request.model_copy(update={'includeTimeline': True}), HISTORY)
    dataset_id = reviewed['reviewDatasetId']
    timeline = reviewed.pop('reviewTimeline')
    assert 'reviewTimeline' not in original and original['reviewDatasetId'] == dataset_id
    assert reviewed == original
    assert dataset_id == sha256((HISTORY / ma_trend_replay.ARCHIVE_NAME).read_bytes()).hexdigest()
    assert len({frame['tradingDate'] for frame in timeline}) == original['scope']['scoreDays']
    assert all(a['at'] < b['at'] for a, b in zip(timeline, timeline[1:]))
    assert all(frame['dailySignalDate'] < frame['tradingDate'] for frame in timeline)


def test_archive_equity_reconciles_with_fees_and_open_position_mark():
    result = replay(ReplayRequest(symbol='FG701', initialCash=100_000, takeProfitPct=1), HISTORY)
    assert result['scope']['scoreDays'] >= 40
    stats = result['metrics']
    assert stats['entryCount'] > 0 and stats['takeProfitCount'] > 0
    assert isclose(stats['realizedPnl'] + stats['unrealizedPnl'] - stats['fees'], stats['netPnl'], abs_tol=.02)
    assert isclose(stats['endingEquity'] - stats['initialCash'], stats['netPnl'], abs_tol=.02)


def test_internal_replay_requires_a_numeric_profit_target():
    app = FastAPI()
    app.include_router(ma_trend_replay.router_for(BoundedSemaphore(1)))
    with TestClient(app) as client:
        path = '/internal/v1/workflows/ma-trend-replay'
        assert client.post(path, json={'symbol': 'FG701', 'initialCash': 100_000}).status_code == 422
        assert client.post(path, json={'symbol': 'FG701', 'initialCash': 100_000, 'takeProfitPct': 0}).status_code == 422
